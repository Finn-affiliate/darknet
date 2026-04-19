import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
from config import DARKNET_TOKEN as TOKEN, ADMIN_ID, CH_SCHWARZMARKT, CH_AUFTRAEGE, CH_KOPFGELDER, CH_LOG

EINTRITT_GEBUEHR = 5000
INSERAT_GEBUEHR  = 0
AUFTRAG_GEBUEHR  = 0
KOPFGELD_GEBUEHR = 0
ENTTARNEN_PREIS  = 50000

try:
    from config import CH_WILLKOMMEN
except ImportError:
    CH_WILLKOMMEN = 0

try:
    from config import CH_WAFFEN, CH_DROGEN, CH_INFOS
except ImportError:
    CH_WAFFEN = 0
    CH_DROGEN = 0
    CH_INFOS = 0
# ──────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def init_db():
    con = sqlite3.connect("darknet.db")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS aliases (
            discord_id TEXT PRIMARY KEY,
            alias TEXT UNIQUE NOT NULL,
            zugelassen INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS inserate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alias TEXT NOT NULL,
            titel TEXT NOT NULL,
            beschreibung TEXT NOT NULL,
            preis INTEGER NOT NULL,
            typ TEXT NOT NULL,
            aktiv INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS kopfgelder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            auftraggeber_alias TEXT NOT NULL,
            ziel_alias TEXT NOT NULL,
            betrag INTEGER NOT NULL,
            aktiv INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS hauskasse (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            betrag INTEGER NOT NULL,
            grund TEXT,
            created_at TEXT
        );
    """)
    con.commit()
    con.close()

def db():
    return sqlite3.connect("darknet.db")

def get_alias(discord_id: str):
    con = db()
    row = con.execute("SELECT alias, zugelassen FROM aliases WHERE discord_id=?", (discord_id,)).fetchone()
    con.close()
    return row

def is_zugelassen(discord_id: str):
    row = get_alias(discord_id)
    return row and row[1] == 1

def hauskasse_add(betrag: int, grund: str):
    con = db()
    con.execute("INSERT INTO hauskasse (betrag, grund, created_at) VALUES (?,?,?)",
                (betrag, grund, datetime.now().isoformat()))
    con.commit()
    con.close()

async def log_msg(text: str, embed: discord.Embed = None):
    if CH_LOG:
        ch = bot.get_channel(CH_LOG)
        if ch:
            await ch.send(f"🔒 `{datetime.now().strftime('%H:%M:%S')}` {text}", embed=embed)

@bot.event
async def on_ready():
    init_db()
    await tree.sync()
    print(f"✅ Darknet Bot online als {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    delete_channels = [CH_SCHWARZMARKT, CH_AUFTRAEGE, CH_KOPFGELDER, CH_WILLKOMMEN]
    if message.channel.id in delete_channels:
        try:
            await message.delete()
        except:
            pass
    await bot.process_commands(message)

@tree.command(name="alias", description="Registriere dich anonym mit einem Alias")
@app_commands.describe(name="Dein gewünschter Alias")
async def alias_cmd(interaction: discord.Interaction, name: str):
    uid = str(interaction.user.id)
    con = db()
    if con.execute("SELECT 1 FROM aliases WHERE discord_id=?", (uid,)).fetchone():
        await interaction.response.send_message("❌ Du hast bereits einen Alias.", ephemeral=True)
        con.close()
        return
    if con.execute("SELECT 1 FROM aliases WHERE alias=?", (name,)).fetchone():
        await interaction.response.send_message("❌ Dieser Alias ist bereits vergeben.", ephemeral=True)
        con.close()
        return
    con.execute("INSERT INTO aliases (discord_id, alias, zugelassen, created_at) VALUES (?,?,0,?)",
                (uid, name, datetime.now().isoformat()))
    con.commit()
    con.close()
    await interaction.response.send_message(
        f"✅ Alias **{name}** registriert.\n📸 Nutze jetzt `/bewerben` und schicke ein Bild deiner Zahlung.",
        ephemeral=True
    )

@tree.command(name="bewerben", description="Bewirb dich mit Zahlungsnachweis (Bild)")
async def bewerben(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    row = get_alias(uid)
    if not row:
        await interaction.response.send_message("❌ Registriere dich zuerst mit `/alias`.", ephemeral=True)
        return
    if row[1] == 1:
        await interaction.response.send_message("✅ Du bist bereits freigeschaltet.", ephemeral=True)
        return
    await interaction.response.send_message(
        "📸 Schicke jetzt ein Bild deines Zahlungsnachweises als normale Nachricht.\n⏳ Du hast 60 Sekunden.",
        ephemeral=True
    )
    def check(m):
        return m.author.id == interaction.user.id and m.attachments
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        attachment = msg.attachments[0]
        embed = discord.Embed(title="📥 Neue Bewerbung", color=0xFF8C00, timestamp=datetime.now())
        embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Alias", value=f"`{row[0]}`", inline=True)
        embed.set_footer(text=f"Freischalten: /freischalten @{interaction.user.name} [betrag]")
        if CH_LOG:
            ch = bot.get_channel(CH_LOG)
            if ch:
                await ch.send(
                    f"🔒 Neue Bewerbung von `{row[0]}`",
                    embed=embed,
                    file=await attachment.to_file()
                )
        try:
            await msg.delete()
        except:
            pass
        await interaction.followup.send("✅ Bewerbung eingegangen! Du wirst benachrichtigt.", ephemeral=True)
    except Exception:
        await interaction.followup.send("⏰ Zeit abgelaufen. Versuche es erneut mit `/bewerben`.", ephemeral=True)

@tree.command(name="freischalten", description="[ADMIN] Spieler freischalten")
@app_commands.describe(user="Discord User", betrag="Eintrittsgeld das er bezahlt hat")
async def freischalten(interaction: discord.Interaction, user: discord.Member, betrag: int):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    uid = str(user.id)
    con = db()
    row = con.execute("SELECT alias FROM aliases WHERE discord_id=?", (uid,)).fetchone()
    if not row:
        await interaction.response.send_message("❌ Kein Alias gefunden.", ephemeral=True)
        con.close()
        return
    con.execute("UPDATE aliases SET zugelassen=1 WHERE discord_id=?", (uid,))
    con.commit()
    con.close()
    mitglied_rolle = discord.utils.get(interaction.guild.roles, name="Mitglied")
    if mitglied_rolle:
        await user.add_roles(mitglied_rolle)
    if betrag > 0:
        hauskasse_add(betrag, f"Eintritt von {row[0]}")
    await interaction.response.send_message(f"✅ `{row[0]}` freigeschaltet.", ephemeral=True)
    try:
        await user.send(f"✅ Du wurdest freigeschaltet. Willkommen im Darknet, **{row[0]}**.")
    except:
        pass
    await log_msg(f"`{row[0]}` freigeschaltet, Eintritt: ${betrag:,}")

@tree.command(name="inserat", description="Erstelle ein Inserat")
@app_commands.describe(titel="Was bietest du an?", beschreibung="Details", preis="Preis in ingame Geld", kanal="Schwarzmarkt / Waffen / Drogen")
@app_commands.choices(kanal=[
    app_commands.Choice(name="Schwarzmarkt", value="schwarzmarkt"),
    app_commands.Choice(name="Waffen", value="waffen"),
    app_commands.Choice(name="Drogen", value="drogen"),
])
async def inserat(interaction: discord.Interaction, titel: str, beschreibung: str, preis: int, kanal: app_commands.Choice[str]):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    alias = get_alias(uid)[0]

    icons = {"schwarzmarkt": "📦", "waffen": "🔫", "drogen": "💊"}
    colors = {"schwarzmarkt": 0x8B0000, "waffen": 0x444444, "drogen": 0x00AA00}
    channels = {"schwarzmarkt": CH_SCHWARZMARKT, "waffen": CH_WAFFEN, "drogen": CH_DROGEN}

    embed = discord.Embed(title=f"{icons[kanal.value]} {titel}", color=colors[kanal.value])
    embed.add_field(name="Beschreibung", value=beschreibung, inline=False)
    embed.add_field(name="Preis", value=f"${preis:,}", inline=True)
    embed.add_field(name="Verkäufer", value=f"`{alias}`", inline=True)

    ch_id = channels[kanal.value]
    if ch_id:
        ch = bot.get_channel(ch_id)
        if ch:
            await ch.send(embed=embed)
    await interaction.response.send_message(f"✅ Inserat in #{kanal.name} erstellt.", ephemeral=True)

@tree.command(name="info", description="Veröffentliche geheime Informationen anonym")
@app_commands.describe(beschreibung="Die Information")
async def info_cmd(interaction: discord.Interaction, beschreibung: str):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    alias = get_alias(uid)[0]

    await interaction.response.send_message(
        "📎 Optional: Schicke jetzt einen Anhang (Bild, Screenshot etc.)\n"
        "Oder tippe `skip` um ohne Anhang fortzufahren.\n⏳ Du hast 60 Sekunden.",
        ephemeral=True
    )

    def check(m):
        return m.author.id == interaction.user.id

    anhang_file = None
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.attachments:
            anhang_file = await msg.attachments[0].to_file()
        try:
            await msg.delete()
        except:
            pass
    except:
        pass

    embed = discord.Embed(title="🗞️ Geheime Information", color=0x1A1A2E)
    embed.add_field(name="Information", value=beschreibung, inline=False)
    embed.add_field(name="Quelle", value=f"`{alias}`", inline=True)

    if CH_INFOS:
        ch = bot.get_channel(CH_INFOS)
        if ch:
            if anhang_file:
                await ch.send(embed=embed, file=anhang_file)
            else:
                await ch.send(embed=embed)
    await interaction.followup.send("✅ Information veröffentlicht.", ephemeral=True)

@tree.command(name="auftrag", description="Schreibe einen anonymen Auftrag aus")
@app_commands.describe(beschreibung="Was soll getan werden?", belohnung="Belohnung in ingame Geld")
async def auftrag(interaction: discord.Interaction, beschreibung: str, belohnung: int):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    alias = get_alias(uid)[0]
    embed = discord.Embed(title="📋 Neuer Auftrag", color=0xFF8C00)
    embed.add_field(name="Details", value=beschreibung, inline=False)
    embed.add_field(name="Belohnung", value=f"${belohnung:,}", inline=True)
    embed.add_field(name="Auftraggeber", value=f"`{alias}` – `/dm {alias}`", inline=True)
    if CH_AUFTRAEGE:
        ch = bot.get_channel(CH_AUFTRAEGE)
        if ch:
            await ch.send(embed=embed)
    await interaction.response.send_message("✅ Auftrag erstellt.", ephemeral=True)

@tree.command(name="kopfgeld", description="Setze ein Kopfgeld auf eine Person")
@app_commands.describe(name="Ingame-Name des Ziels", betrag="Kopfgeld in ingame Geld", zusatzinfo="Telefonnummer, Adresse, etc. (optional)")
async def kopfgeld(interaction: discord.Interaction, name: str, betrag: int, zusatzinfo: str = None):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    alias = get_alias(uid)[0]

    await interaction.response.send_message(
        "📸 Optional: Schicke jetzt ein Bild des Ziels (Screenshot etc.)\n"
        "Oder tippe `skip` um ohne Bild fortzufahren.\n⏳ Du hast 60 Sekunden.",
        ephemeral=True
    )

    def check(m):
        return m.author.id == interaction.user.id

    bild_file = None
    try:
        msg = await bot.wait_for("message", check=check, timeout=60)
        if msg.attachments:
            bild_file = await msg.attachments[0].to_file()
        try:
            await msg.delete()
        except:
            pass
    except:
        pass

    embed = discord.Embed(title="💀 Neues Kopfgeld", color=0xFF0000)
    embed.add_field(name="Ziel", value=name, inline=True)
    embed.add_field(name="Betrag", value=f"${betrag:,}", inline=True)
    embed.add_field(name="Auftraggeber", value=f"`{alias}` – `/dm {alias}`", inline=True)
    if zusatzinfo:
        embed.add_field(name="Zusatzinfo", value=zusatzinfo, inline=False)

    if CH_KOPFGELDER:
        ch = bot.get_channel(CH_KOPFGELDER)
        if ch:
            if bild_file:
                await ch.send(embed=embed, file=bild_file)
            else:
                await ch.send(embed=embed)
    await interaction.followup.send("✅ Kopfgeld gesetzt.", ephemeral=True)

@tree.command(name="dm", description="Sende eine anonyme Nachricht an einen Alias")
@app_commands.describe(ziel="Alias des Empfängers", nachricht="Deine Nachricht")
async def anon_dm(interaction: discord.Interaction, ziel: str, nachricht: str):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    con = db()
    ziel_row = con.execute("SELECT discord_id FROM aliases WHERE alias=? AND zugelassen=1", (ziel,)).fetchone()
    con.close()
    if not ziel_row:
        await interaction.response.send_message("❌ Alias nicht gefunden.", ephemeral=True)
        return
    ziel_user = bot.get_user(int(ziel_row[0]))
    if not ziel_user:
        await interaction.response.send_message("❌ Konnte Benutzer nicht erreichen.", ephemeral=True)
        return
    try:
        absender_alias = get_alias(uid)[0]
        embed = discord.Embed(title="📬 Anonyme Nachricht", description=nachricht, color=0x333333)
        embed.set_footer(text=f"Absender: {absender_alias} – Antworten: /dm {absender_alias} [nachricht]")
        await ziel_user.send(embed=embed)
        await interaction.response.send_message("✅ Nachricht anonym zugestellt.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Konnte Nachricht nicht zustellen.", ephemeral=True)

@tree.command(name="enttarnen", description=f"Enttarne einen Alias (kostet ${ENTTARNEN_PREIS:,} ingame)")
@app_commands.describe(alias="Alias der enttarnt werden soll")
async def enttarnen(interaction: discord.Interaction, alias: str):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    anfragen_alias = get_alias(uid)[0]

    await interaction.response.send_message(
        f"💸 Sende **${ENTTARNEN_PREIS:,}** ingame an **Philipp Hildebrand** und schicke danach ein Bild der Überweisung.\n"
        f"⏳ Du hast **10 Minuten.**",
        ephemeral=True
    )

    def check(m):
        return m.author.id == interaction.user.id and m.attachments

    try:
        msg = await bot.wait_for("message", check=check, timeout=600)
        attachment = msg.attachments[0]
        embed = discord.Embed(title="🔍 Enttarnen-Anfrage", color=0xFF0000, timestamp=datetime.now())
        embed.add_field(name="Anfragender", value=f"`{anfragen_alias}`", inline=True)
        embed.add_field(name="Ziel-Alias", value=f"`{alias}`", inline=True)
        hauskasse_add(ENTTARNEN_PREIS, f"Enttarnen: {anfragen_alias} -> {alias}")
        if CH_LOG:
            ch = bot.get_channel(CH_LOG)
            if ch:
                await ch.send(
                    f"⚠️ Enttarnen-Anfrage: `{anfragen_alias}` will `{alias}` enttarnen",
                    embed=embed,
                    file=await attachment.to_file()
                )
        try:
            await msg.delete()
        except:
            pass
        await interaction.followup.send("✅ Zahlung eingegangen. Du wirst kontaktiert.", ephemeral=True)
    except:
        await interaction.followup.send("⏰ Zeit abgelaufen. Versuche es erneut.", ephemeral=True)

@tree.command(name="kasse", description="[ADMIN] Hauskasse anzeigen")
async def kasse(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    con = db()
    total = con.execute("SELECT SUM(betrag) FROM hauskasse").fetchone()[0] or 0
    letzte = con.execute("SELECT betrag, grund FROM hauskasse ORDER BY id DESC LIMIT 5").fetchall()
    con.close()
    embed = discord.Embed(title="💰 Hauskasse", color=0x00FF00)
    embed.add_field(name="Total", value=f"${total:,}", inline=False)
    log_text = "\n".join([f"`${r[0]:,}` – {r[1]}" for r in letzte]) or "Keine Einträge"
    embed.add_field(name="Letzte Transaktionen", value=log_text, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="lookup", description="[ADMIN] Echte Identity hinter Alias anzeigen")
@app_commands.describe(alias="Alias zum nachschlagen")
async def lookup(interaction: discord.Interaction, alias: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    con = db()
    row = con.execute("SELECT discord_id FROM aliases WHERE alias=?", (alias,)).fetchone()
    con.close()
    if not row:
        await interaction.response.send_message("❌ Alias nicht gefunden.", ephemeral=True)
        return
    user = bot.get_user(int(row[0]))
    await interaction.response.send_message(
        f"🔍 `{alias}` → {user.mention if user else row[0]} (`{row[0]}`)",
        ephemeral=True
    )

@tree.command(name="setup", description="[ADMIN] Server einrichten")
async def setup(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return
    await interaction.response.send_message("⚙️ Richte Server ein...", ephemeral=True)
    guild = interaction.guild
    for channel in guild.channels:
        try:
            await channel.delete()
        except:
            pass
    await guild.default_role.edit(permissions=discord.Permissions.none())
    mitglied_rolle = await guild.create_role(name="Mitglied", color=discord.Color.dark_red())
    admin_rolle = await guild.create_role(name="Admin", color=discord.Color.gold(), permissions=discord.Permissions.all())
    everyone  = guild.default_role
    deny_all  = discord.PermissionOverwrite(read_messages=False, send_messages=False)
    open_rw   = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    member_ro = discord.PermissionOverwrite(read_messages=True, send_messages=False)
    admin_rw  = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
    cat_welcome = await guild.create_category("👋 WILLKOMMEN", overwrites={
        everyone: open_rw, mitglied_rolle: open_rw
    })
    willkommen_ch = await guild.create_text_channel("willkommen", category=cat_welcome, overwrites={
        everyone: open_rw, admin_rolle: admin_rw
    }, topic="Registriere dich mit /alias und bewirb dich mit /bewerben")
    cat_markt = await guild.create_category("🕶️ UNTERGRUND", overwrites={
        everyone: deny_all, mitglied_rolle: discord.PermissionOverwrite(read_messages=True)
    })
    schwarzmarkt_ch = await guild.create_text_channel("schwarzmarkt", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Allgemeiner Schwarzmarkt")
    waffen_ch = await guild.create_text_channel("waffen", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Waffen & Munition")
    drogen_ch = await guild.create_text_channel("drogen", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Drogen & Substanzen")
    infos_ch = await guild.create_text_channel("geheime-infos", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Geheime Informationen")
    auftraege_ch = await guild.create_text_channel("auftraege", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Anonyme Auftraege")
    kopfgelder_ch = await guild.create_text_channel("kopfgelder", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Aktive Kopfgelder")
    befehle_ch = await guild.create_text_channel("befehle", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: open_rw, admin_rolle: admin_rw
    }, topic="Hier Commands eingeben")
    cat_admin = await guild.create_category("🔒 ADMIN", overwrites={
        everyone: deny_all, mitglied_rolle: deny_all, admin_rolle: admin_rw
    })
    log_ch = await guild.create_text_channel("admin-log", category=cat_admin, overwrites={
        everyone: deny_all, mitglied_rolle: deny_all, admin_rolle: admin_rw
    })
    await guild.owner.add_roles(admin_rolle)
    result = f"""✅ **Server eingerichtet!**

**Fuege diese IDs in deine config.py ein:**
```
CH_WILLKOMMEN   = {willkommen_ch.id}
CH_SCHWARZMARKT = {schwarzmarkt_ch.id}
CH_WAFFEN       = {waffen_ch.id}
CH_DROGEN       = {drogen_ch.id}
CH_INFOS        = {infos_ch.id}
CH_AUFTRAEGE    = {auftraege_ch.id}
CH_KOPFGELDER   = {kopfgelder_ch.id}
CH_LOG          = {log_ch.id}
```"""
    await log_ch.send(result)

bot.run(TOKEN)
