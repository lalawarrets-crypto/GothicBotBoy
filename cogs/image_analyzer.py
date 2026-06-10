"""
Listener automático de imágenes — solo en canales configurados.
"""
import io
import asyncio
import urllib.request

import discord
from discord.ext import commands

from database.db import upsert_user, add_image, find_duplicate_hash, update_score, get_user
from services.exif_service import extract_exif
from services.hash_service import compute_phash
from services.ai_detection import check_ai_image
from cogs.catfish_config import is_monitored, get_log_channel_id

SCORE_NO_EXIF = 10
SCORE_AI_HIGH = 35
SCORE_DUPLICATE = 50
SCORE_ACCOUNT_NEW = 30
SCORE_ACCOUNT_MEDIUM = 15


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
        # Solo canales configurados
        if not is_monitored(message.channel.id):
            return
        # Whitelist: score negativo
        db_user = get_user(message.author.id)
        if db_user and db_user.get("score", 0) < 0:
            return

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

        upsert_user(
            user.id, str(user),
            join_date=user.joined_at.isoformat() if user.joined_at else None,
            account_created=user.created_at.isoformat(),
        )

        try:
            image_bytes = await attachment.read()
        except:
            return

        results = await asyncio.to_thread(self._run_analysis, image_bytes, attachment.url)

        score_add = 0
        flags = []

        # EXIF
        if not results["exif"]["has_exif"]:
            score_add += SCORE_NO_EXIF
            flags.append("❌ Sin metadatos EXIF")
        else:
            cam = results["exif"].get("camera", "")
            flags.append(f"✅ EXIF: {cam}" if cam else "✅ EXIF presente")

        # AI
        ai_score = results["ai"]["ai_score"]
        if ai_score > 0.5:
            score_add += SCORE_AI_HIGH
            flags.append(f"⚠️ IA detectada: {int(ai_score*100)}%")
        elif results["ai"]["error"]:
            flags.append(f"⚙️ IA: {results['ai']['error']}")
        else:
            flags.append(f"✅ IA: {int(ai_score*100)}% (normal)")

        # Hash duplicado
        duplicate = None
        if results["phash"]:
            duplicate = find_duplicate_hash(results["phash"], exclude_user=user.id)
            if duplicate:
                score_add += SCORE_DUPLICATE
                flags.append(f"🔴 Imagen duplicada (usada por <@{duplicate['user_id']}>)")
            else:
                flags.append("✅ Imagen única")

        # Edad de cuenta
        age = _account_age_days(user)
        if age < 30:
            score_add += SCORE_ACCOUNT_NEW
            flags.append(f"🔴 Cuenta nueva: {age} días")
        elif age < 90:
            score_add += SCORE_ACCOUNT_MEDIUM
            flags.append(f"🟡 Cuenta reciente: {age} días")
        else:
            flags.append(f"✅ Cuenta: {age} días")

        # Guardar en DB
        add_image(
            user_id=user.id, message_id=message.id,
            channel_id=message.channel.id, url=attachment.url,
            phash=results["phash"], has_exif=results["exif"]["has_exif"],
            exif_camera=results["exif"].get("camera"),
            exif_software=results["exif"].get("software"),
            ai_score=ai_score, ai_type=results["ai"]["ai_type"],
            duplicate_of=duplicate["user_id"] if duplicate else None,
        )

        # Actualizar score
        existing = get_user(user.id)
        old_score = existing["score"] if existing else 0
        new_score = old_score + score_add
        update_score(user.id, new_score)

        if new_score < 26:
            return

        await self._send_alert(message, user, new_score, flags, results, attachment)

    def _run_analysis(self, image_bytes, image_url):
        return {
            "exif": extract_exif(image_bytes),
            "phash": compute_phash(image_bytes),
            "ai": check_ai_image(image_url),
        }

    async def _send_alert(self, message, user, score, flags, results, attachment):
        if score >= 76:
            color = 0xFF0000
            level = "🔴 CATFISH PROBABLE"
        elif score >= 51:
            color = 0xFF8800
            level = "🟠 ALTO RIESGO"
        elif score >= 26:
            color = 0xFFCC00
            level = "🟡 SOSPECHOSO"
        else:
            return

        embed = discord.Embed(title=f"{level} — Score: {score}", color=color)
        embed.set_author(name=f"{user} ({user.id})", icon_url=user.display_avatar.url)

        analysis_text = "\n".join(flags)
        embed.add_field(name="📸 Análisis", value=analysis_text, inline=False)

        age = _account_age_days(user)
        embed.add_field(name="👤 Usuario", value=(
            f"**Cuenta:** {age} días\n"
            f"**En servidor:** {user.joined_at.strftime('%Y-%m-%d') if user.joined_at else '?'}\n"
            f"**Canal:** {message.channel.mention}"
        ), inline=True)

        exif = results["exif"]
        exif_text = "Sin metadatos"
        if exif["has_exif"]:
            parts = []
            if exif["camera"]: parts.append(f"📷 {exif['camera']}")
            if exif["software"]: parts.append(f"💻 {exif['software']}")
            if exif["date"]: parts.append(f"📅 {exif['date']}")
            if exif["gps"]: parts.append("📍 GPS presente")
            exif_text = "\n".join(parts) if parts else "Presente"
        embed.add_field(name="📋 EXIF", value=exif_text, inline=True)

        if attachment:
            embed.set_thumbnail(url=attachment.url)
        embed.set_footer(text="Anti-Catfish | Zona Gothic")

        # Canal de logs desde config
        log_ch_id = get_log_channel_id()
        log_channel = None
        if log_ch_id:
            log_channel = message.guild.get_channel(int(log_ch_id))

        if log_channel:
            view = ModActionView(user.id)
            await log_channel.send(embed=embed, view=view)

        # Auto-mute si score >= 76
        if score >= 76:
            muted_role = discord.utils.get(message.guild.roles, name="Muted")
            if muted_role:
                try:
                    await user.add_roles(muted_role, reason=f"Anti-Catfish: score {score}")
                except:
                    pass


class ModActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.target_id = user_id

    @discord.ui.button(label="✅ Aprobar", style=discord.ButtonStyle.success, custom_id="catfish_approve")
    async def approve(self, interaction: discord.Interaction, button):
        from database.db import update_score, add_mod_action
        update_score(self.target_id, 0)
        add_mod_action(self.target_id, interaction.user.id, "approve")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Aprobado por {interaction.user.mention}", view=self)

    @discord.ui.button(label="⚠️ Advertir", style=discord.ButtonStyle.secondary, custom_id="catfish_warn")
    async def warn(self, interaction: discord.Interaction, button):
        from database.db import add_mod_action
        add_mod_action(self.target_id, interaction.user.id, "warn")
        member = interaction.guild.get_member(int(self.target_id))
        if member:
            try:
                await member.send(
                    "⚠️ **Advertencia Anti-Catfish**\n━━━━━━━━━━━━━━\n"
                    "Se detectó actividad sospechosa en tu cuenta.\n━━━━━━━━━━━━━━")
            except: pass
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"⚠️ Advertido por {interaction.user.mention}", view=self)

    @discord.ui.button(label="🔨 Ban", style=discord.ButtonStyle.danger, custom_id="catfish_ban")
    async def ban(self, interaction: discord.Interaction, button):
        from database.db import add_mod_action
        add_mod_action(self.target_id, interaction.user.id, "ban")
        member = interaction.guild.get_member(int(self.target_id))
        if member:
            try: await member.send("🔴 **Has sido baneado por catfish detectado.**")
            except: pass
            try: await interaction.guild.ban(member, reason="Anti-Catfish: catfish confirmado")
            except: pass
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🔨 Baneado por {interaction.user.mention}", view=self)


async def setup(bot):
    await bot.add_cog(ImageAnalyzerCog(bot))
