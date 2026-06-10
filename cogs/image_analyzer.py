"""
Listener automático — análisis forense POR IMAGEN.
Cada imagen se evalúa individualmente. Solo alerta si UNA imagen es sospechosa.
"""
import io
import asyncio

import discord
from discord.ext import commands

from database.db import upsert_user, add_image, find_duplicate_hash, get_user
from services.exif_service import extract_exif
from services.hash_service import compute_phash
from services.ai_detection import check_ai_image
from services.ela_service import analyze_ela
from services.local_analysis import analyze_local
from services.reverse_search import search_image
from cogs.catfish_config import is_monitored, get_log_channel_id


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
            return
        if db_user and db_user.get("verified"):
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
                print(f"[Analyzer] Error: {e}")
            finally:
                self._analyzing.discard(att.id)

    async def _analyze_image(self, message, attachment):
        user = message.author
        if not message.guild:
            return

        upsert_user(user.id, str(user),
            join_date=user.joined_at.isoformat() if user.joined_at else None,
            account_created=user.created_at.isoformat())

        try:
            image_bytes = await attachment.read()
        except:
            return

        r = await asyncio.to_thread(self._full_analysis, image_bytes, attachment.url)

        # === SCORE POR IMAGEN (no acumulativo) ===
        img_score = 0
        flags = []

        # EXIF
        exif = r["exif"]
        if not exif["has_exif"]:
            img_score += 5
            flags.append("⚠️ Sin EXIF")
        else:
            cam = exif.get("camera", "")
            flags.append(f"✅ EXIF: {cam}" if cam else "✅ EXIF presente")
            if exif.get("gps"):
                flags.append("📍 GPS")
                img_score -= 5
        if exif.get("software"):
            sw = exif["software"].lower()
            if any(x in sw for x in ["photoshop", "gimp", "lightroom", "canva", "picsart", "facetune", "meitu"]):
                img_score += 15
                flags.append(f"🔴 Editada: {exif['software']}")

        # IA API
        ai = r["ai"]
        if ai["ai_score"] > 0.7:
            img_score += 40
            flags.append(f"🔴 IA: {int(ai['ai_score']*100)}%")
        elif ai["ai_score"] > 0.5:
            img_score += 25
            flags.append(f"⚠️ Posible IA: {int(ai['ai_score']*100)}%")
        elif ai.get("error"):
            flags.append(f"⚙️ API: {ai['error'][:30]}")
        else:
            flags.append(f"✅ IA: {int(ai['ai_score']*100)}%")

        # ELA
        ela = r["ela"]
        if ela["score"] > 60:
            img_score += 20
            flags.append(f"🔴 ELA: manipulación ({ela['score']}%)")
        elif ela["score"] > 30:
            img_score += 8
            flags.append(f"🟡 ELA: posible edición ({ela['score']}%)")

        # Local — solo flags realmente importantes
        local = r["local"]
        for f in local["flags"]:
            if "METADATO IA" in f:
                img_score += 40
                flags.append(f)
            elif "Dimensiones típicas de IA" in f:
                img_score += 15
                flags.append(f)
            elif "Ratio 1:1" in f:
                img_score += 8
                flags.append(f)

        # BÚSQUEDA INVERSA — links para verificar
        rev = r["reverse"]
        self._reverse_links = rev.get("links", {})

        # HASH DUPLICADO
        duplicate = None
        phash = r["phash"]
        if phash:
            duplicate = find_duplicate_hash(phash, exclude_user=user.id)
            if duplicate:
                img_score += 50
                flags.append(f"🔴 DUPLICADA — foto de <@{duplicate['user_id']}>")

        # CUENTA — solo penaliza si es MUY nueva
        age = _account_age_days(user)
        if age < 7:
            img_score += 20
            flags.append(f"🔴 Cuenta: {age} días")
        elif age < 30:
            img_score += 10
            flags.append(f"🟡 Cuenta: {age} días")
        elif age > 365:
            img_score -= 10  # Cuenta vieja = más confiable

        img_score = max(0, img_score)

        # Guardar en DB
        add_image(user_id=user.id, message_id=message.id,
            channel_id=message.channel.id, url=attachment.url,
            phash=phash, has_exif=exif["has_exif"],
            exif_camera=exif.get("camera"), exif_software=exif.get("software"),
            ai_score=ai["ai_score"], ai_type=ai["ai_type"],
            duplicate_of=duplicate["user_id"] if duplicate else None)

        # Solo alertar si ESTA imagen es sospechosa (>=30)
        if img_score >= 30:
            await self._send_alert(message, user, img_score, flags, r, attachment)

    def _full_analysis(self, image_bytes, image_url):
        return {
            "exif": extract_exif(image_bytes),
            "phash": compute_phash(image_bytes),
            "ai": check_ai_image(image_url),
            "ela": analyze_ela(image_bytes),
            "local": analyze_local(image_bytes),
            "reverse": search_image(image_url),
        }

    async def _send_alert(self, message, user, img_score, flags, r, attachment):
        if img_score >= 60:
            color, level = 0xFF0000, "🔴 MUY SOSPECHOSO"
        elif img_score >= 45:
            color, level = 0xFF8800, "🟠 SOSPECHOSO"
        else:
            color, level = 0xFFCC00, "🟡 ATENCIÓN"

        embed = discord.Embed(title=f"{level} — Score: {img_score}", color=color)
        embed.set_author(name=f"{user} ({user.id})", icon_url=user.display_avatar.url)

        flags_text = "\n".join(flags[:15])
        embed.add_field(name="🔍 Análisis", value=flags_text[:1024], inline=False)

        age = _account_age_days(user)
        embed.add_field(name="👤", value=(
            f"Cuenta: {age}d\n{message.channel.mention}\n[Ir]({message.jump_url})"
        ), inline=True)

        embed.add_field(name="📊", value=(
            f"ELA: {r['ela']['score']}%\n"
            f"IA: {int(r['ai']['ai_score']*100)}%\n"
            f"**Score: {img_score}**"
        ), inline=True)

        # Links de búsqueda inversa
        rev_links = getattr(self, "_reverse_links", {})
        if rev_links:
            links_text = "\n".join(f"[{name}]({url})" for name, url in rev_links.items())
            embed.add_field(name="🌐 Verificar en internet", value=links_text, inline=False)

        if attachment:
            embed.set_thumbnail(url=attachment.url)
        embed.set_footer(text="Anti-Catfish v2 | Score por imagen")

        log_ch_id = get_log_channel_id()
        if log_ch_id:
            ch = message.guild.get_channel(int(log_ch_id))
            if ch:
                await ch.send(embed=embed, view=ModActionView(user.id))

        # Auto-mute solo si score >= 60 Y cuenta < 30 días
        if img_score >= 60 and age < 30:
            muted = discord.utils.get(message.guild.roles, name="Muted")
            if muted:
                try: await user.add_roles(muted, reason=f"Anti-Catfish: {img_score}")
                except: pass


class ModActionView(discord.ui.View):
    def __init__(self, uid):
        super().__init__(timeout=None)
        self.tid = uid

    @discord.ui.button(label="✅ OK", style=discord.ButtonStyle.success, custom_id="cf_ok")
    async def ok(self, i, b):
        from database.db import update_score, add_mod_action
        update_score(self.tid, 0); add_mod_action(self.tid, i.user.id, "approve")
        for x in self.children: x.disabled = True
        await i.response.edit_message(content=f"✅ OK por {i.user.mention}", view=self)

    @discord.ui.button(label="⚠️ Advertir", style=discord.ButtonStyle.secondary, custom_id="cf_w")
    async def w(self, i, b):
        from database.db import add_mod_action
        add_mod_action(self.tid, i.user.id, "warn")
        m = i.guild.get_member(int(self.tid))
        if m:
            try: await m.send("⚠️ **Anti-Catfish** — Actividad sospechosa detectada.")
            except: pass
        for x in self.children: x.disabled = True
        await i.response.edit_message(content=f"⚠️ Advertido por {i.user.mention}", view=self)

    @discord.ui.button(label="🔍 Verificar", style=discord.ButtonStyle.primary, custom_id="cf_v")
    async def v(self, i, b):
        await i.response.send_message(f"Usa `/verify <@{self.tid}>`", ephemeral=True)

    @discord.ui.button(label="🔨 Ban", style=discord.ButtonStyle.danger, custom_id="cf_b")
    async def ban(self, i, b):
        from database.db import add_mod_action
        add_mod_action(self.tid, i.user.id, "ban")
        m = i.guild.get_member(int(self.tid))
        if m:
            try: await m.send("🔴 **Baneado por catfish.**")
            except: pass
            try: await i.guild.ban(m, reason="Anti-Catfish")
            except: pass
        for x in self.children: x.disabled = True
        await i.response.edit_message(content=f"🔨 Ban por {i.user.mention}", view=self)


async def setup(bot):
    await bot.add_cog(ImageAnalyzerCog(bot))
