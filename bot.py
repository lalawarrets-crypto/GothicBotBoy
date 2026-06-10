"""
Zona Gothic — Gothic Bot Boy 💜
Bot anti-catfish + administración.
"""
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("GUILD_ID", "")


# === HTTP Server (mantiene vivo en hosting) ===

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Boy online")

    def log_message(self, *args):
        pass


def start_ping_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), PingHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"[HTTP] Puerto {port}")
    except:
        print("[HTTP] No se pudo iniciar (OK en DisCloud)")


# === Bot ===

class GothicBotBoy(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🔍 Anti-Catfish | Zona Gothic",
            ),
        )

    async def setup_hook(self):
        # Inicializar DB
        from database.db import init_db
        init_db()

        # Cargar cogs
        await self.load_extension("cogs.image_analyzer")
        await self.load_extension("cogs.profile_checker")

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print("[OK] Comandos sincronizados")

    async def on_ready(self):
        print("=" * 40)
        print(f"  𝕲𝖔𝖙𝖍𝖎𝖈 𝕭𝖔𝖙 𝕭𝖔𝖞 💜")
        print(f"  Anti-Catfish System")
        print(f"  Bot ID: {self.user.id}")
        print(f"  Servidores: {len(self.guilds)}")
        print("=" * 40)


bot = GothicBotBoy()


@bot.tree.command(name="ping", description="Test de conexión")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🏓 Pong! `{round(bot.latency * 1000)}ms`", ephemeral=True)


if __name__ == "__main__":
    print("[*] Iniciando Gothic Bot Boy...")
    start_ping_server()
    bot.run(TOKEN)
