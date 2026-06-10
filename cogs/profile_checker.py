"""
Comandos /check, /investigate, /score, /leaderboard, /stats, /whitelist.
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database.db import get_user, get_user_images, get_name_changes, get_stats, upsert_user, update_score, _conn
from services.behavior_tracker import analyze_behavior


def _account_age(user):
    days = (datetime.now(timezone.utc) - user.created_at).days
    if days < 30: return f"🔴 {days} días", days
    elif days < 90: return f"🟡 {days} días", days
    else: return f"🟢 {days} días", days


class ProfileCheckerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Trackear cambios de nombre/avatar."""
        if before.display_name != after.display_name:
            from database.db import add_name_change
            add_name_change(after.id, before.display_name, after.display_name)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Auto-check cuando alguien entra al servidor."""
        upsert_user(member.id, str(member),
            join_date=member.joined_at.isoformat() if member.joined_at else None,
            account_created=member.created_at.isoformat())
        age = (datetime.now(timezone.utc) - member.created_at).days
        if age < 7:
            from cogs.catfish_config import get_log_channel_id
            log_ch_id = get_log_channel_id()
            if log_ch_id:
                ch = member.guild.get_channel(int(log_ch_id))
                if ch:
                    embed = discord.Embed(
                        title="🆕 Cuenta nueva entró al servidor",
                        description=f"**{member.mention}** — cuenta de **{age} días**",
                        color=0xFF0000 if age < 3 else 0xFFAA00,
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.add_field(name="Creada", value=member.created_at.strftime("%Y-%m-%d %H:%M"), inline=True)
                    embed.set_footer(text="Anti-Catfish | Auto-Check")
                    await ch.send(embed=embed)

    @app_commands.command(name="check", description="Análisis rápido anti-catfish")
    @app_commands.describe(usuario="Usuario a analizar")
    async def check_user(self, interaction: discord.Interaction, usuario: discord.Member):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        upsert_user(usuario.id, str(usuario),
            join_date=usuario.joined_at.isoformat() if usuario.joined_at else None,
            account_created=usuario.created_at.isoformat())

        db_user = get_user(usuario.id)
        score = db_user["score"] if db_user else 0
        images = get_user_images(usuario.id, limit=10)
        age_text, _ = _account_age(usuario)

        if score >= 76: color, risk = 0xFF0000, "🔴 CATFISH PROBABLE"
        elif score >= 51: color, risk = 0xFF8800, "🟠 ALTO RIESGO"
        elif score >= 26: color, risk = 0xFFCC00, "🟡 SOSPECHOSO"
        else: color, risk = 0x2ECC71, "🟢 NORMAL"

        verified = "✅ Verificado" if (db_user and db_user.get("verified")) else "❌ No verificado"

        embed = discord.Embed(title=f"🔍 {usuario.display_name}", color=color)
        embed.set_thumbnail(url=usuario.display_avatar.url)
        embed.add_field(name="Score", value=f"**{score}** — {risk}", inline=False)
        embed.add_field(name="👤 Info", value=f"Cuenta: {age_text}\nEstado: {verified}", inline=True)

        if images:
            no_exif = sum(1 for i in images if not i.get("has_exif"))
            ai_flags = sum(1 for i in images if i.get("ai_score", 0) > 0.5)
            dups = sum(1 for i in images if i.get("duplicate_of"))
            embed.add_field(name=f"📸 {len(images)} fotos", value=(
                f"Sin EXIF: {no_exif}\nIA detect: {ai_flags}\nDuplicadas: {dups}"
            ), inline=True)

        embed.set_footer(text="Anti-Catfish | /investigate para análisis profundo")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="investigate", description="Investigación profunda anti-catfish")
    @app_commands.describe(usuario="Usuario a investigar")
    async def investigate(self, interaction: discord.Interaction, usuario: discord.Member):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        upsert_user(usuario.id, str(usuario),
            join_date=usuario.joined_at.isoformat() if usuario.joined_at else None,
            account_created=usuario.created_at.isoformat())

        db_user = get_user(usuario.id)
        score = db_user["score"] if db_user else 0
        images = get_user_images(usuario.id, limit=50)
        name_changes = get_name_changes(usuario.id)
        behavior = analyze_behavior(usuario.id)
        age_text, age_days = _account_age(usuario)

        if score >= 76: color = 0xFF0000
        elif score >= 51: color = 0xFF8800
        elif score >= 26: color = 0xFFCC00
        else: color = 0x2ECC71

        embed = discord.Embed(
            title=f"🔎 INVESTIGACIÓN — {usuario.display_name}",
            color=color,
        )
        embed.set_thumbnail(url=usuario.display_avatar.url)

        # Score
        embed.add_field(name="📊 Score Total", value=f"**{score}**", inline=True)
        verified = "✅" if (db_user and db_user.get("verified")) else "❌"
        embed.add_field(name="Verificado", value=verified, inline=True)
        embed.add_field(name="Cuenta", value=age_text, inline=True)

        # Historial de imágenes
        if images:
            no_exif = sum(1 for i in images if not i.get("has_exif"))
            with_exif = len(images) - no_exif
            ai_flags = sum(1 for i in images if i.get("ai_score", 0) > 0.5)
            dups = sum(1 for i in images if i.get("duplicate_of"))
            avg_ai = sum(i.get("ai_score", 0) for i in images) / len(images)

            img_text = (
                f"📸 Total: **{len(images)}**\n"
                f"✅ Con EXIF: {with_exif} | ❌ Sin: {no_exif}\n"
                f"🤖 IA detectada: {ai_flags}\n"
                f"🔁 Duplicadas: {dups}\n"
                f"📈 IA promedio: {int(avg_ai*100)}%"
            )
            embed.add_field(name="📸 Análisis de imágenes", value=img_text, inline=False)

            # Últimas 5 fotos detalladas
            details = ""
            for img in images[:5]:
                ai_pct = int(img.get("ai_score", 0) * 100)
                exif_icon = "✅" if img.get("has_exif") else "❌"
                dup_icon = "🔴" if img.get("duplicate_of") else "✅"
                cam = img.get("exif_camera", "")[:20] if img.get("exif_camera") else ""
                details += f"`{exif_icon}EXIF {dup_icon}DUP 🤖{ai_pct}%` {cam}\n"
            if details:
                embed.add_field(name="📋 Últimas fotos", value=details, inline=False)

        # Cambios de nombre
        if name_changes:
            nc = "\n".join(f"`{c['old_name']}` → `{c['new_name']}`" for c in name_changes[:5])
            embed.add_field(name=f"📝 Cambios de nombre ({len(name_changes)})", value=nc, inline=False)

        # Comportamiento
        if behavior["flags"]:
            embed.add_field(name="🧠 Comportamiento", value="\n".join(behavior["flags"]), inline=False)

        embed.set_footer(text="Anti-Catfish | Investigación Forense Completa")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="Top usuarios más sospechosos")
    async def leaderboard(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)

        conn = _conn()
        rows = conn.execute(
            "SELECT discord_id, username, score, verified FROM users WHERE score > 0 ORDER BY score DESC LIMIT 15"
        ).fetchall()
        conn.close()

        if not rows:
            return await interaction.response.send_message("✅ Sin usuarios sospechosos.", ephemeral=True)

        text = ""
        for i, row in enumerate(rows):
            s = row["score"]
            if s >= 76: emoji = "🔴"
            elif s >= 51: emoji = "🟠"
            elif s >= 26: emoji = "🟡"
            else: emoji = "⚪"
            v = " ✅" if row["verified"] else ""
            text += f"`{i+1}.` {emoji} **{row['username'][:20]}** — Score: **{s}**{v}\n"

        embed = discord.Embed(
            title="🏆 Leaderboard Anti-Catfish",
            description=text,
            color=0xFF6600,
        )
        embed.set_footer(text="Usuarios ordenados por score de sospecha")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="score", description="Ver score de sospecha")
    @app_commands.describe(usuario="Usuario")
    async def score_cmd(self, interaction: discord.Interaction, usuario: discord.Member):
        db_user = get_user(usuario.id)
        score = db_user["score"] if db_user else 0
        emoji = "🔴" if score >= 76 else "🟠" if score >= 51 else "🟡" if score >= 26 else "🟢"
        await interaction.response.send_message(
            f"{emoji} **{usuario.display_name}** — Score: **{score}**", ephemeral=True)

    @app_commands.command(name="stats", description="Estadísticas anti-catfish")
    async def stats_cmd(self, interaction: discord.Interaction):
        s = get_stats()
        embed = discord.Embed(title="📊 Anti-Catfish Stats", color=0xFFD700)
        embed.add_field(name="📸 Imágenes", value=str(s["total_images"]), inline=True)
        embed.add_field(name="👤 Usuarios", value=str(s["total_users"]), inline=True)
        embed.add_field(name="⚠️ Flaggeados", value=str(s["flagged"]), inline=True)
        embed.add_field(name="🤖 IA detectada", value=str(s["ai_detected"]), inline=True)
        embed.add_field(name="🔁 Duplicados", value=str(s["duplicates"]), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="whitelist", description="Excluir/incluir del análisis")
    @app_commands.describe(usuario="Usuario", accion="add o remove")
    async def whitelist_cmd(self, interaction: discord.Interaction, usuario: discord.Member, accion: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Solo admin.", ephemeral=True)
        upsert_user(usuario.id, str(usuario))
        if accion.lower() == "add":
            update_score(usuario.id, -999)
            await interaction.response.send_message(f"✅ {usuario.mention} excluido.", ephemeral=True)
        elif accion.lower() == "remove":
            update_score(usuario.id, 0)
            await interaction.response.send_message(f"✅ {usuario.mention} re-incluido.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Usa `add` o `remove`.", ephemeral=True)

    @app_commands.command(name="reset_score", description="[Admin] Resetear score de un usuario")
    @app_commands.describe(usuario="Usuario")
    async def reset_score(self, interaction: discord.Interaction, usuario: discord.Member):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Solo admin.", ephemeral=True)
        update_score(usuario.id, 0)
        await interaction.response.send_message(f"✅ Score de {usuario.mention} reseteado a 0.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCheckerCog(bot))
