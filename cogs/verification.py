"""
Sistema de verificación anti-catfish con desafíos.
"""
import random
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from database.db import get_user, upsert_user, update_score
from services.exif_service import extract_exif

GESTURES = [
    "mostrando 3 dedos",
    "con el pulgar arriba",
    "haciendo el signo de paz ✌",
    "tocándote la oreja derecha",
    "con la mano en la frente",
    "mostrando la palma de tu mano",
    "señalando hacia arriba",
]

WORDS = [
    "GOTHIC", "LUNA", "ROJO", "FUEGO", "SOMBRA",
    "NOCHE", "REAL", "DARK", "SOUL", "VAMPIRO",
    "STORM", "BLADE", "CROW", "ONYX", "VENOM",
]


class VerificationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pending = {}  # user_id -> challenge info

    @app_commands.command(name="verify", description="[Mod] Enviar desafío de verificación a un usuario")
    @app_commands.describe(usuario="Usuario a verificar")
    async def verify_cmd(self, interaction: discord.Interaction, usuario: discord.Member):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Sin permisos.", ephemeral=True)

        if usuario.bot:
            return await interaction.response.send_message("❌ No puedes verificar bots.", ephemeral=True)

        gesture = random.choice(GESTURES)
        word = random.choice(WORDS)
        challenge = f"una selfie {gesture} y un papel que diga **{word}**"

        self.pending[usuario.id] = {
            "gesture": gesture,
            "word": word,
            "requested_by": interaction.user.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guild_id": interaction.guild.id,
        }

        # DM al usuario
        try:
            embed = discord.Embed(
                title="🔍 Verificación Anti-Catfish",
                description=(
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"Un moderador de **{interaction.guild.name}** ha solicitado\n"
                    f"que verifiques tu identidad.\n\n"
                    f"📸 **Envía {challenge}**\n\n"
                    f"Envía la foto como respuesta a este mensaje.\n"
                    f"La foto debe ser tomada AHORA (no vale screenshot).\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0xFFAA00,
            )
            embed.set_footer(text="Anti-Catfish | Zona Gothic")
            await usuario.send(embed=embed)

            await interaction.response.send_message(
                f"✅ Desafío enviado al DM de {usuario.mention}\n"
                f"**Desafío:** {challenge}\n"
                f"Cuando responda, recibirás el resultado aquí.",
                ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ {usuario.mention} tiene los DMs cerrados.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Detecta respuestas de verificación por DM."""
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author.id not in self.pending:
            return
        if not message.attachments:
            return

        challenge = self.pending[message.author.id]
        att = message.attachments[0]

        if not att.content_type or not att.content_type.startswith("image/"):
            await message.channel.send("❌ Envía una imagen, no otro tipo de archivo.")
            return

        # Analizar la foto de verificación
        try:
            image_bytes = await att.read()
        except:
            return

        exif = extract_exif(image_bytes)

        # Resultados
        checks = []
        verified = True

        if exif["has_exif"]:
            checks.append("✅ EXIF presente — foto tomada con cámara/teléfono")
            if exif["camera"]:
                checks.append(f"  📷 Dispositivo: {exif['camera']}")
            if exif["date"]:
                checks.append(f"  📅 Fecha: {exif['date']}")
        else:
            checks.append("⚠️ Sin EXIF — posible screenshot o descarga")
            verified = False

        if exif.get("software"):
            sw = exif["software"].lower()
            if any(x in sw for x in ["photoshop", "gimp", "lightroom", "canva"]):
                checks.append(f"🔴 Editada con: {exif['software']}")
                verified = False
            else:
                checks.append(f"📱 Software: {exif['software']}")

        checks.append(f"\n📋 Desafío: {challenge['gesture']} + papel con {challenge['word']}")
        checks.append("⚠️ Un moderador verificará visualmente la foto")

        # Enviar resultado al mod
        guild = self.bot.get_guild(challenge["guild_id"])
        if guild:
            from cogs.catfish_config import get_log_channel_id
            log_ch_id = get_log_channel_id()
            log_channel = guild.get_channel(int(log_ch_id)) if log_ch_id else None

            if log_channel:
                embed = discord.Embed(
                    title=f"📸 Verificación — {message.author}",
                    description="\n".join(checks),
                    color=0x2ECC71 if verified else 0xFFAA00,
                )
                embed.set_image(url=att.url)
                embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
                embed.add_field(name="Solicitado por", value=f"<@{challenge['requested_by']}>", inline=True)
                embed.add_field(name="EXIF", value="✅ Sí" if exif["has_exif"] else "❌ No", inline=True)
                embed.set_footer(text="Anti-Catfish | Verificación")

                view = VerifyResultView(message.author.id)
                await log_channel.send(embed=embed, view=view)

        await message.channel.send(
            "✅ Foto recibida. Un moderador la revisará. Gracias por cooperar.")

        del self.pending[message.author.id]


class VerifyResultView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.target_id = user_id

    @discord.ui.button(label="✅ Verificado", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button):
        upsert_user(self.target_id, "verified")
        update_score(self.target_id, 0)
        # Marcar como verificado en DB
        import sqlite3
        from database.db import _conn
        conn = _conn()
        conn.execute("UPDATE users SET verified=1, score=0 WHERE discord_id=?", (str(self.target_id),))
        conn.commit()
        conn.close()

        member = interaction.guild.get_member(int(self.target_id))
        if member:
            try: await member.send("✅ **¡Verificación aprobada!** Tu identidad ha sido confirmada.")
            except: pass

        for item in self.children: item.disabled = True
        await interaction.response.edit_message(
            content=f"✅ Verificado por {interaction.user.mention}", view=self)

    @discord.ui.button(label="❌ Rechazado", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button):
        update_score(self.target_id, 100)
        member = interaction.guild.get_member(int(self.target_id))
        if member:
            try: await member.send("❌ **Verificación rechazada.** Contacta a un moderador si crees que es un error.")
            except: pass

        for item in self.children: item.disabled = True
        await interaction.response.edit_message(
            content=f"❌ Rechazado por {interaction.user.mention} — Score a 100", view=self)


async def setup(bot):
    await bot.add_cog(VerificationCog(bot))
