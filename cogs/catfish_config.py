"""
Configuracion del sistema anti-catfish.
Comandos para canal de logs y canales monitoreados.
Persistencia via GitHub.
"""
import os
import json
import base64
import urllib.request as urlreq

import discord
from discord import app_commands
from discord.ext import commands

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
CONFIG_FILE = os.path.join(DATA_PATH, "catfish_config.json")


def load_catfish_config():
    os.makedirs(DATA_PATH, exist_ok=True)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {"log_channel": "", "monitored_channels": []}


def save_catfish_config(cfg):
    os.makedirs(DATA_PATH, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    try:
        _backup_to_github()
    except Exception as e:
        print(f"[CatfishConfig] Backup error: {e}")


def _backup_to_github():
    gh_token = os.getenv("GITHUB_TOKEN", "")
    gh_repo = os.getenv("GITHUB_REPO", "")
    if not gh_token or not gh_repo:
        return

    with open(CONFIG_FILE, "r") as f:
        content = f.read()

    encoded = base64.b64encode(content.encode()).decode()
    api_url = f"https://api.github.com/repos/{gh_repo}/contents/data/catfish_config.json"

    sha = ""
    try:
        r = urlreq.Request(api_url, headers={
            "Authorization": f"token {gh_token}",
            "Accept": "application/vnd.github.v3+json",
        })
        resp = json.loads(urlreq.urlopen(r, timeout=10).read())
        sha = resp.get("sha", "")
    except:
        pass

    payload = json.dumps({
        "message": "backup catfish_config",
        "content": encoded,
        "branch": "main",
        **({"sha": sha} if sha else {}),
    })

    r = urlreq.Request(api_url, data=payload.encode(), headers={
        "Authorization": f"token {gh_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
    }, method="PUT")
    urlreq.urlopen(r, timeout=10)
    print("[CatfishConfig] Backup OK")


def restore_from_github():
    if os.path.exists(CONFIG_FILE):
        return

    gh_token = os.getenv("GITHUB_TOKEN", "")
    gh_repo = os.getenv("GITHUB_REPO", "")
    if not gh_token or not gh_repo:
        return

    try:
        api_url = f"https://api.github.com/repos/{gh_repo}/contents/data/catfish_config.json"
        r = urlreq.Request(api_url, headers={
            "Authorization": f"token {gh_token}",
            "Accept": "application/vnd.github.v3+json",
        })
        resp = json.loads(urlreq.urlopen(r, timeout=10).read())
        content = base64.b64decode(resp["content"]).decode()
        os.makedirs(DATA_PATH, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            f.write(content)
        print("[CatfishConfig] Restaurado de GitHub")
    except:
        print("[CatfishConfig] Sin backup previo")


def is_monitored(channel_id):
    cfg = load_catfish_config()
    channels = cfg.get("monitored_channels", [])
    if not channels:
        return False
    return str(channel_id) in [str(c) for c in channels]


def get_log_channel_id():
    cfg = load_catfish_config()
    return cfg.get("log_channel", "")


class CatfishConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        restore_from_github()

    catfish_group = app_commands.Group(name="catfish", description="Configurar sistema anti-catfish")

    @catfish_group.command(name="logs", description="[Owner] Canal donde llegan las alertas")
    @app_commands.describe(canal="Canal de alertas anti-catfish")
    async def set_logs(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ Solo el dueño.", ephemeral=True)
        cfg = load_catfish_config()
        cfg["log_channel"] = str(canal.id)
        save_catfish_config(cfg)
        await interaction.response.send_message(
            f"✅ Alertas anti-catfish → {canal.mention}", ephemeral=True)

    @catfish_group.command(name="agregar", description="[Owner] Agregar canal a monitorear")
    @app_commands.describe(canal="Canal donde se analizarán las fotos")
    async def add_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ Solo el dueño.", ephemeral=True)
        cfg = load_catfish_config()
        channels = cfg.setdefault("monitored_channels", [])
        cid = str(canal.id)
        if cid in [str(c) for c in channels]:
            return await interaction.response.send_message(
                f"⚠ {canal.mention} ya está monitoreado.", ephemeral=True)
        channels.append(int(cid))
        save_catfish_config(cfg)
        await interaction.response.send_message(
            f"✅ {canal.mention} agregado al monitoreo.", ephemeral=True)

    @catfish_group.command(name="quitar", description="[Owner] Quitar canal del monitoreo")
    @app_commands.describe(canal="Canal a quitar")
    async def remove_channel(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ Solo el dueño.", ephemeral=True)
        cfg = load_catfish_config()
        channels = cfg.get("monitored_channels", [])
        cid = int(canal.id)
        cfg["monitored_channels"] = [c for c in channels if int(c) != cid]
        save_catfish_config(cfg)
        await interaction.response.send_message(
            f"✅ {canal.mention} quitado del monitoreo.", ephemeral=True)

    @catfish_group.command(name="ver", description="[Owner] Ver configuración actual")
    async def view_config(self, interaction: discord.Interaction):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message("❌ Solo el dueño.", ephemeral=True)
        cfg = load_catfish_config()
        log_ch = cfg.get("log_channel", "")
        channels = cfg.get("monitored_channels", [])

        text = "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "🔍 **𝐀𝐍𝐓𝐈-𝐂𝐀𝐓𝐅𝐈𝐒𝐇**\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        text += f"📋 Logs: {f'<#{log_ch}>' if log_ch else '❌ Sin configurar'}\n\n"
        text += f"**Canales monitoreados ({len(channels)}):**\n"
        if channels:
            for cid in channels:
                text += f"  📺 <#{cid}>\n"
        else:
            text += "  Ninguno\n"
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━"
        await interaction.response.send_message(text, ephemeral=True)


async def setup(bot):
    await bot.add_cog(CatfishConfigCog(bot))
