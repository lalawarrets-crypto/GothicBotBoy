"""
Comandos /check y /investigate para analizar perfiles.
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database.db import get_user, get_user_images, get_name_changes, get_stats, upsert_user


def _account_age(user):
    days = (datetime.now(timezone.utc) - user.created_at).days
    if days < 30:
        return f"🔴 {days} días", days
    elif days < 90:
        return f"🟡 {days} días", days
    else:
        return f"🟢 {days} días", days


class ProfileCheckerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="check", description="Análisis rápido anti-catfish de un usuario")
    @app_commands.describe(usuario="Usuario a analizar")
    async def check_user(self, interaction: discord.Interaction, usuario: discord.Member):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Registrar
        upsert_user(usuario.id, str(usuario),
                     join_date=usuario.joined_at.isoformat() if usuario.joined_at else None,
                     account_created=usuario.created_at.isoformat())

        db_user = get_user(usuario.id)
        score = db_user["score"] if db_user else 0
        images = get_user_images(usuario.id, limit=5)
        name_changes = get_name_changes(usuario.id)

        age_text, age_days = _account_age(usuario)

        # Color por score
        if score >= 76:
            color = 0xFF0000
            risk = "🔴 CATFISH PROBABLE"
        elif score >= 51:
            color = 0xFF8800
            risk = "🟠 ALTO RIESGO"
        elif score >= 26:
            color = 0xFFCC00
            risk = "🟡 SOSPECHOSO"
        else:
            color = 0x2ECC71
            risk = "🟢 NORMAL"

        embed = discord.Embed(title=f"🔍 Check — {usuario.display_name}", color=color)
        embed.set_thumbnail(url=usuario.display_avatar.url)

        embed.add_field(name="Score", value=f"**{score}** — {risk}", inline=False)

        embed.add_field(name="👤 Info", value=(
            f"**Cuenta:** {age_text}\n"
            f"**En servidor:** {usuario.joined_at.strftime('%Y-%m-%d') if usuario.joined_at else '?'}\n"
            f"**Verificado:** {'✅' if (db_user and db_user.get('verified')) else '❌'}"
        ), inline=True)

        # Imágenes analizadas
        if images:
            img_text = ""
            for img in images[:5]:
                ai = img.get("ai_score", 0)
                exif = "✅" if img.get("has_exif") else "❌"
                dup = "🔴DUP" if img.get("duplicate_of") else "✅"
                img_text += f"EXIF:{exif} IA:{int(ai*100)}% {dup}\n"
            embed.add_field(name=f"📸 Imágenes ({len(images)})", value=img_text, inline=True)
        else:
            embed.add_field(name="📸 Imágenes", value="Sin análisis previos", inline=True)

        # Cambios de nombre
        if name_changes:
            nc_text = "\n".join(f"`{nc['old_name']}` → `{nc['new_name']}`" for nc in name_changes[:3])
            embed.add_field(name="📝 Cambios de nombre", value=nc_text, inline=False)

        embed.set_footer(text="Anti-Catfish | Zona Gothic")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="score", description="Ver score de sospecha de un usuario")
    @app_commands.describe(usuario="Usuario a consultar")
    async def score_cmd(self, interaction: discord.Interaction, usuario: discord.Member):
        db_user = get_user(usuario.id)
        score = db_user["score"] if db_user else 0

        if score >= 76:
            emoji = "🔴"
        elif score >= 51:
            emoji = "🟠"
        elif score >= 26:
            emoji = "🟡"
        else:
            emoji = "🟢"

        await interaction.response.send_message(
            f"{emoji} **{usuario.display_name}** — Score: **{score}**", ephemeral=True)

    @app_commands.command(name="stats", description="Estadísticas del sistema anti-catfish")
    async def stats_cmd(self, interaction: discord.Interaction):
        s = get_stats()
        embed = discord.Embed(title="📊 Anti-Catfish Stats", color=0xFFD700)
        embed.add_field(name="📸 Imágenes analizadas", value=str(s["total_images"]), inline=True)
        embed.add_field(name="👤 Usuarios trackeados", value=str(s["total_users"]), inline=True)
        embed.add_field(name="⚠️ Flaggeados (>50)", value=str(s["flagged"]), inline=True)
        embed.add_field(name="🤖 IA detectada", value=str(s["ai_detected"]), inline=True)
        embed.add_field(name="🔁 Duplicados", value=str(s["duplicates"]), inline=True)
        embed.set_footer(text="Anti-Catfish | Zona Gothic")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="whitelist", description="Excluir/incluir usuario del análisis")
    @app_commands.describe(usuario="Usuario", accion="add o remove")
    async def whitelist_cmd(self, interaction: discord.Interaction, usuario: discord.Member, accion: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Solo admin.", ephemeral=True)
        from database.db import update_score
        if accion.lower() == "add":
            upsert_user(usuario.id, str(usuario))
            update_score(usuario.id, -999)  # score negativo = whitelist
            await interaction.response.send_message(f"✅ {usuario.mention} excluido del análisis.", ephemeral=True)
        elif accion.lower() == "remove":
            update_score(usuario.id, 0)
            await interaction.response.send_message(f"✅ {usuario.mention} re-incluido.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Usa `add` o `remove`.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ProfileCheckerCog(bot))
