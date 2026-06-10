"""
Zona Gothic — Gothic Bot Boy 💜
Sistema Anti-Catfish Avanzado.
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
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"[HTTP] Puerto {port}")
    except:
        print("[HTTP] Skipped")


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
                name="🔍 Anti-Catfish",
            ),
        )

    async def setup_hook(self):
        from database.db import init_db
        init_db()

        await self.load_extension("cogs.catfish_config")
        await self.load_extension("cogs.image_analyzer")
        await self.load_extension("cogs.video_analyzer")
        await self.load_extension("cogs.profile_checker")
        await self.load_extension("cogs.verification")

        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print("[OK] Comandos sincronizados")

    async def on_ready(self):
        print("=" * 45)
        print("  𝕲𝖔𝖙𝖍𝖎𝖈 𝕭𝖔𝖙 𝕭𝖔𝖞 💜 — Anti-Catfish v2")
        print(f"  Bot: {self.user.id} | Servers: {len(self.guilds)}")
        print("=" * 45)


bot = GothicBotBoy()


@bot.tree.command(name="ping", description="Test de conexión")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🏓 Pong! `{round(bot.latency * 1000)}ms`", ephemeral=True)


if __name__ == "__main__":
    print("[*] Iniciando Anti-Catfish System...")
    start_ping_server()
    bot.run(TOKEN)
