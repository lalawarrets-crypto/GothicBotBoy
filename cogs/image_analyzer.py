"""
Listener automático de imágenes — análisis forense completo.
EXIF + Hash duplicado + ELA + IA + Comportamiento.
"""
import io
import asyncio

import discord
from discord.ext import commands

from database.db import upsert_user, add_image, find_duplicate_hash, update_score, get_user
from services.exif_service import extract_exif
from services.hash_service import compute_phash
from services.ai_detection import check_ai_image
from services.ela_service import analyze_ela
from services.behavior_tracker import analyze_behavior
from cogs.catfish_config import is_monitored, get_log_channel_id

# Scoring
POINTS = {
    "no_exif": 10,
    "ai_high": 35,
    "ai_medium": 15,
    "duplicate": 50,
    "account_new": 30,
    "account_medium": 15,
    "ela_manipulated": 20,
    "ela_suspicious": 10,
    "edited_software": 15,
}


def _account_age_days(user):
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) - user.created_at).days


class ImageAnalyzerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._analyzing = set()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if not message.attachments:
            return
        if not is_monitored(message.channel.id):
            return
        db_user = get_user(message.author.id)
        if db_user and db_user.get("score", 0) < 0:
            return  # Whitelist
        if db_user and db_user.get("verified"):
            return  # Ya verificado

        for att in message.attachments:
            if not att.content_type or not att.content_type.startswith("image/"):
                continue
            if att.size > 10 * 1024 * 1024:
                continue
            if att.id in self._analyzing:
                continue
            self._analyzing.add(att.id)
            try:
                await self._analyze_image(message, att)
            except Exception as e:
                print(f"[ImageAnalyzer] Error: {e}")
            finally:
                self._analyzing.discard(att.id)

    async def _analyze_image(self, message, attachment):
        user = message.author
        guild = message.guild
        if not guild:
            return

        upsert_user(user.id, str(user),
            join_date=user.joined_at.isoformat() if user.joined_at else None,
            account_created=user.created_at.isoformat())

        try:
            image_bytes = await attachment.read()
        except:
            return

        results = await asyncio.to_thread(self._run_analysis, image_bytes, attachment.url)

        score_add = 0
        flags = []

        # === EXIF ===
        exif = results["exif"]
        if not exif["has_exif"]:
            score_add += POINTS["no_exif"]
            flags.append("❌ Sin EXIF — probable descarga de internet")
        else:
            cam = exif.get("camera", "")
            if cam:
                flags.append(f"✅ Dispositivo: {cam}")
            else:
                flags.append("✅ EXIF presente")
            if exif.get("gps"):
                flags.append("📍 GPS detectado en imagen")

        # Software de edición
        if exif.get("software"):
            sw = exif["software"].lower()
            if any(x in sw for x in ["photoshop", "gimp", "lightroom", "canva", "picsart", "facetune"]):
                score_add += POINTS["edited_software"]
                flags.append(f"🔴 Editada con: {exif['software']}")

        # === IA Detection ===
        ai = results["ai"]
        ai_score = ai["ai_score"]
        if ai_score > 0.7:
            score_add += POINTS["ai_high"]
            flags.append(f"🔴 IA detectada: {int(ai_score*100)}%")
        elif ai_score > 0.5:
            score_add += POINTS["ai_medium"]
            flags.append(f"⚠️ Posible IA: {int(ai_score*100)}%")
        elif ai.get("error"):
            flags.append(f"⚙️ IA: {ai['error'][:50]}")
        else:
            flags.append(f"✅ IA: {int(ai_score*100)}%")

        # === ELA ===
        ela = results["ela"]
        if ela["manipulated"]:
            if ela["score"] > 60:
                score_add += POINTS["ela_manipulated"]
                flags.append(f"🔴 ELA: manipulación detectada ({ela['score']}%)")
            else:
                score_add += POINTS["ela_suspicious"]
                flags.append(f"🟡 ELA: posible edición ({ela['score']}%)")
        else:
            flags.append(f"✅ ELA: sin manipulación ({ela['score']}%)")

        # === Hash duplicado ===
        duplicate = None
        phash = results["phash"]
        if phash:
            duplicate = find_duplicate_hash(phash, exclude_user=user.id)
            if duplicate:
                score_add += POINTS["duplicate"]
                flags.append(f"🔴 DUPLICADA — misma foto usada por <@{duplicate['user_id']}>")
            else:
                flags.append("✅ Imagen única")

        # === Edad de cuenta ===
        age = _account_age_days(user)
        if age < 30:
            score_add += POINTS["account_new"]
            flags.append(f"🔴 Cuenta: {age} días")
        elif age < 90:
            score_add += POINTS["account_medium"]
            flags.append(f"🟡 Cuenta: {age} días")
        else:
            flags.append(f"✅ Cuenta: {age} días")

        # === Comportamiento ===
        behavior = results["behavior"]
        if behavior["flags"]:
            score_add += behavior["score"]
            flags.extend(behavior["flags"])

        # Guardar
        add_image(
            user_id=user.id, message_id=message.id,
            channel_id=message.channel.id, url=attachment.url,
            phash=phash, has_exif=exif["has_exif"],
            exif_camera=exif.get("camera"), exif_software=exif.get("software"),
            ai_score=ai_score, ai_type=ai["ai_type"],
            duplicate_of=duplicate["user_id"] if duplicate else None,
        )

        existing = get_user(user.id)
        old_score = existing["score"] if existing else 0
        new_score = old_score + score_add
        update_score(user.id, new_score)

        if new_score < 26:
            return

        await self._send_alert(message, user, new_score, score_add, flags, results, attachment)

    def _run_analysis(self, image_bytes, image_url):
        return {
            "exif": extract_exif(image_bytes),
            "phash": compute_phash(image_bytes),
            "ai": check_ai_image(image_url),
            "ela": analyze_ela(image_bytes),
            "behavior": {"flags": [], "score": 0},  # se calcula después
        }

    async def _send_alert(self, message, user, score, score_add, flags, results, attachment):
        if score >= 76:
            color, level = 0xFF0000, "🔴 CATFISH PROBABLE"
        elif score >= 51:
            color, level = 0xFF8800, "🟠 ALTO RIESGO"
        else:
            color, level = 0xFFCC00, "🟡 SOSPECHOSO"

        embed = discord.Embed(title=f"{level} — Score: {score} (+{score_add})", color=color)
        embed.set_author(name=f"{user} ({user.id})", icon_url=user.display_avatar.url)

        # Dividir flags en chunks si son muchos
        flags_text = "\n".join(flags[:15])
        embed.add_field(name="🔍 Análisis completo", value=flags_text[:1024], inline=False)

        age = _account_age_days(user)
        embed.add_field(name="👤 Info", value=(
            f"Cuenta: {age} días\n"
            f"Canal: {message.channel.mention}\n"
            f"[Ver mensaje]({message.jump_url})"
        ), inline=True)

        ela = results["ela"]
        embed.add_field(name="📊 Scores", value=(
            f"ELA: {ela['score']}%\n"
            f"IA: {int(results['ai']['ai_score']*100)}%\n"
            f"Total: **{score}**"
        ), inline=True)

        if attachment:
            embed.set_thumbnail(url=attachment.url)
        embed.set_footer(text="Anti-Catfish | Zona Gothic | Análisis Forense")

        log_ch_id = get_log_channel_id()
        if log_ch_id:
            log_channel = message.guild.get_channel(int(log_ch_id))
            if log_channel:
                view = ModActionView(user.id)
                await log_channel.send(embed=embed, view=view)

        if score >= 76:
            muted_role = discord.utils.get(message.guild.roles, name="Muted")
            if muted_role:
                try: await user.add_roles(muted_role, reason=f"Anti-Catfish: score {score}")
                except: pass


class ModActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.target_id = user_id

    @discord.ui.button(label="✅ Aprobar", style=discord.ButtonStyle.success, custom_id="cf_approve")
    async def approve(self, interaction, button):
        from database.db import update_score, add_mod_action
        update_score(self.target_id, 0)
        add_mod_action(self.target_id, interaction.user.id, "approve")
        for i in self.children: i.disabled = True
        await interaction.response.edit_message(content=f"✅ Aprobado por {interaction.user.mention}", view=self)

    @discord.ui.button(label="⚠️ Advertir", style=discord.ButtonStyle.secondary, custom_id="cf_warn")
    async def warn(self, interaction, button):
        from database.db import add_mod_action
        add_mod_action(self.target_id, interaction.user.id, "warn")
        m = interaction.guild.get_member(int(self.target_id))
        if m:
            try: await m.send("⚠️ **Advertencia Anti-Catfish** — Actividad sospechosa detectada.")
            except: pass
        for i in self.children: i.disabled = True
        await interaction.response.edit_message(content=f"⚠️ Advertido por {interaction.user.mention}", view=self)

    @discord.ui.button(label="🔍 Verificar", style=discord.ButtonStyle.primary, custom_id="cf_verify")
    async def verify(self, interaction, button):
        await interaction.response.send_message(
            f"Usa `/verify <@{self.target_id}>` para enviar desafío de verificación.", ephemeral=True)

    @discord.ui.button(label="🔨 Ban", style=discord.ButtonStyle.danger, custom_id="cf_ban")
    async def ban(self, interaction, button):
        from database.db import add_mod_action
        add_mod_action(self.target_id, interaction.user.id, "ban")
        m = interaction.guild.get_member(int(self.target_id))
        if m:
            try: await m.send("🔴 **Baneado por catfish.**")
            except: pass
            try: await interaction.guild.ban(m, reason="Anti-Catfish")
            except: pass
        for i in self.children: i.disabled = True
        await interaction.response.edit_message(content=f"🔨 Baneado por {interaction.user.mention}", view=self)


async def setup(bot):
    await bot.add_cog(ImageAnalyzerCog(bot))
