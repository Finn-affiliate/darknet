import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
import random
import string
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
from config import DARKNET_TOKEN as TOKEN, ADMIN_ID
EINTRITT_GEBUEHR = 5000       # Ingame Geld für Eintritt (manuell du gibst frei)
INSERAT_GEBUEHR = 500         # Kosten pro Inserat (Schwarzmarkt)
AUFTRAG_GEBUEHR = 300         # Kosten pro Auftrag
KOPFGELD_GEBUEHR = 200        # Kosten pro Kopfgeld
ENTTARNEN_PREIS = 50000       # Kosten um jemanden zu enttarnen

# Channel IDs (nach Server-Setup eintragen)
CH_SCHWARZMARKT = 0
CH_AUFTRAEGE = 0
CH_KOPFGELDER = 0
CH_LOG = 0  # Privater Admin-Log Channel
# ──────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ─── DATABASE ─────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect("darknet.db")
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS aliases (
            discord_id TEXT PRIMARY KEY,
            alias TEXT UNIQUE NOT NULL,
            guthaben INTEGER DEFAULT 0,
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

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_alias(discord_id: str):
    con = db()
    row = con.execute("SELECT alias, guthaben, zugelassen FROM aliases WHERE discord_id=?", (discord_id,)).fetchone()
    con.close()
    return row

def is_zugelassen(discord_id: str):
    row = get_alias(discord_id)
    return row and row[2] == 1

def hauskasse_add(betrag: int, grund: str):
    con = db()
    con.execute("INSERT INTO hauskasse (betrag, grund, created_at) VALUES (?,?,?)",
                (betrag, grund, datetime.now().isoformat()))
    con.commit()
    con.close()

async def log(bot, text: str):
    if CH_LOG:
        ch = bot.get_channel(CH_LOG)
        if ch:
            await ch.send(f"🔒 `{datetime.now().strftime('%H:%M:%S')}` {text}")

# ─── EVENTS ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    init_db()
    await tree.sync()
    print(f"✅ Darknet Bot online als {bot.user}")

# ─── ALIAS REGISTRIEREN ───────────────────────────────────────────────────────
@tree.command(name="alias", description="Registriere dich mit einem anonymen Alias")
@app_commands.describe(name="Dein gewünschter Alias (wird öffentlich sichtbar)")
async def alias_cmd(interaction: discord.Interaction, name: str):
    uid = str(interaction.user.id)
    con = db()

    existing = con.execute("SELECT alias FROM aliases WHERE discord_id=?", (uid,)).fetchone()
    if existing:
        await interaction.response.send_message("❌ Du hast bereits einen Alias.", ephemeral=True)
        con.close()
        return

    name_taken = con.execute("SELECT 1 FROM aliases WHERE alias=?", (name,)).fetchone()
    if name_taken:
        await interaction.response.send_message("❌ Dieser Alias ist bereits vergeben.", ephemeral=True)
        con.close()
        return

    con.execute("INSERT INTO aliases (discord_id, alias, zugelassen, created_at) VALUES (?,?,0,?)",
                (uid, name, datetime.now().isoformat()))
    con.commit()
    con.close()

    await interaction.response.send_message(
        f"✅ Alias **{name}** registriert.\n⏳ Warte auf Freischaltung durch den Admin.",
        ephemeral=True
    )
    await log(bot, f"Neuer Alias-Antrag: `{name}` von `{interaction.user}`")

# ─── ADMIN: FREISCHALTEN ──────────────────────────────────────────────────────
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

    hauskasse_add(betrag, f"Eintritt von {row[0]}")

    await interaction.response.send_message(f"✅ `{row[0]}` freigeschaltet. {betrag} zur Hauskasse.", ephemeral=True)
    try:
        await user.send(f"✅ Du wurdest freigeschaltet. Willkommen im Darknet, **{row[0]}**.")
    except:
        pass
    await log(bot, f"`{row[0]}` freigeschaltet, Eintritt: {betrag}")

# ─── SCHWARZMARKT INSERAT ─────────────────────────────────────────────────────
@tree.command(name="inserat", description="Erstelle ein Inserat auf dem Schwarzmarkt")
@app_commands.describe(titel="Was bietest du an?", beschreibung="Details", preis="Preis in ingame Geld")
async def inserat(interaction: discord.Interaction, titel: str, beschreibung: str, preis: int):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return

    alias = get_alias(uid)[0]
    con = db()
    con.execute("INSERT INTO inserate (alias, titel, beschreibung, preis, typ, created_at) VALUES (?,?,?,?,'schwarzmarkt',?)",
                (alias, titel, beschreibung, preis, datetime.now().isoformat()))
    con.commit()
    con.close()

    hauskasse_add(INSERAT_GEBUEHR, f"Inserat von {alias}: {titel}")

    embed = discord.Embed(title=f"📦 {titel}", color=0x8B0000)
    embed.add_field(name="Beschreibung", value=beschreibung, inline=False)
    embed.add_field(name="Preis", value=f"${preis:,}", inline=True)
    embed.add_field(name="Verkäufer", value=f"`{alias}`", inline=True)
    embed.set_footer(text=f"Gebühr: ${INSERAT_GEBUEHR} wurde verrechnet")

    if CH_SCHWARZMARKT:
        ch = bot.get_channel(CH_SCHWARZMARKT)
        if ch:
            await ch.send(embed=embed)

    await interaction.response.send_message(f"✅ Inserat erstellt. Gebühr: ${INSERAT_GEBUEHR}", ephemeral=True)

# ─── AUFTRAG AUSSCHREIBEN ─────────────────────────────────────────────────────
@tree.command(name="auftrag", description="Schreibe einen anonymen Auftrag aus")
@app_commands.describe(beschreibung="Was soll getan werden?", belohnung="Belohnung in ingame Geld")
async def auftrag(interaction: discord.Interaction, beschreibung: str, belohnung: int):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return

    alias = get_alias(uid)[0]
    con = db()
    con.execute("INSERT INTO inserate (alias, titel, beschreibung, preis, typ, created_at) VALUES (?,?,?,?,'auftrag',?)",
                (alias, "Auftrag", beschreibung, belohnung, datetime.now().isoformat()))
    con.commit()
    con.close()

    hauskasse_add(AUFTRAG_GEBUEHR, f"Auftrag von {alias}")

    embed = discord.Embed(title="📋 Neuer Auftrag", color=0xFF8C00)
    embed.add_field(name="Details", value=beschreibung, inline=False)
    embed.add_field(name="Belohnung", value=f"${belohnung:,}", inline=True)
    embed.add_field(name="Auftraggeber", value="`[ANONYM]`", inline=True)
    embed.set_footer(text=f"Gebühr: ${AUFTRAG_GEBUEHR} wurde verrechnet")

    if CH_AUFTRAEGE:
        ch = bot.get_channel(CH_AUFTRAEGE)
        if ch:
            await ch.send(embed=embed)

    await interaction.response.send_message(f"✅ Auftrag erstellt. Gebühr: ${AUFTRAG_GEBUEHR}", ephemeral=True)

# ─── KOPFGELD ─────────────────────────────────────────────────────────────────
@tree.command(name="kopfgeld", description="Setze ein Kopfgeld auf einen Alias")
@app_commands.describe(ziel="Alias des Ziels", betrag="Kopfgeld in ingame Geld")
async def kopfgeld(interaction: discord.Interaction, ziel: str, betrag: int):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return

    alias = get_alias(uid)[0]
    con = db()

    ziel_exists = con.execute("SELECT 1 FROM aliases WHERE alias=? AND zugelassen=1", (ziel,)).fetchone()
    if not ziel_exists:
        await interaction.response.send_message("❌ Ziel nicht gefunden.", ephemeral=True)
        con.close()
        return

    con.execute("INSERT INTO kopfgelder (auftraggeber_alias, ziel_alias, betrag, created_at) VALUES (?,?,?,?)",
                (alias, ziel, betrag, datetime.now().isoformat()))
    con.commit()
    con.close()

    hauskasse_add(KOPFGELD_GEBUEHR, f"Kopfgeld von {alias} auf {ziel}")

    embed = discord.Embed(title="💀 Neues Kopfgeld", color=0xFF0000)
    embed.add_field(name="Ziel", value=f"`{ziel}`", inline=True)
    embed.add_field(name="Betrag", value=f"${betrag:,}", inline=True)
    embed.add_field(name="Auftraggeber", value="`[ANONYM]`", inline=True)
    embed.set_footer(text=f"Gebühr: ${KOPFGELD_GEBUEHR} wurde verrechnet")

    if CH_KOPFGELDER:
        ch = bot.get_channel(CH_KOPFGELDER)
        if ch:
            await ch.send(embed=embed)

    await interaction.response.send_message(f"✅ Kopfgeld gesetzt. Gebühr: ${KOPFGELD_GEBUEHR}", ephemeral=True)

# ─── ANONYME NACHRICHT ────────────────────────────────────────────────────────
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
        embed = discord.Embed(title="📬 Anonyme Nachricht", description=nachricht, color=0x333333)
        embed.set_footer(text="Absender: [UNBEKANNT]")
        await ziel_user.send(embed=embed)
        await interaction.response.send_message("✅ Nachricht anonym zugestellt.", ephemeral=True)
    except:
        await interaction.response.send_message("❌ Konnte Nachricht nicht zustellen.", ephemeral=True)

# ─── ENTTARNEN ────────────────────────────────────────────────────────────────
@tree.command(name="enttarnen", description=f"Enttarne einen Alias (kostet ${ENTTARNEN_PREIS:,} ingame)")
@app_commands.describe(alias="Alias der enttarnt werden soll")
async def enttarnen(interaction: discord.Interaction, alias: str):
    uid = str(interaction.user.id)
    if not is_zugelassen(uid):
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return

    # Nur Admin sieht das Ergebnis – Spieler meldet sich beim Admin
    anfragen_alias = get_alias(uid)[0]
    hauskasse_add(ENTTARNEN_PREIS, f"Enttarnen-Anfrage: {anfragen_alias} → {alias}")

    await interaction.response.send_message(
        f"✅ Anfrage eingegangen. ${ENTTARNEN_PREIS:,} wurden verrechnet.\nDu wirst kontaktiert.",
        ephemeral=True
    )
    await log(bot, f"⚠️ Enttarnen-Anfrage: `{anfragen_alias}` will `{alias}` enttarnen")

# ─── ADMIN: HAUSKASSE ─────────────────────────────────────────────────────────
@tree.command(name="kasse", description="[ADMIN] Hauskasse anzeigen")
async def kasse(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return

    con = db()
    total = con.execute("SELECT SUM(betrag) FROM hauskasse").fetchone()[0] or 0
    letzte = con.execute("SELECT betrag, grund, created_at FROM hauskasse ORDER BY id DESC LIMIT 5").fetchall()
    con.close()

    embed = discord.Embed(title="💰 Hauskasse", color=0x00FF00)
    embed.add_field(name="Total", value=f"${total:,}", inline=False)
    log_text = "\n".join([f"`${r[0]:,}` – {r[1]}" for r in letzte]) or "Keine Einträge"
    embed.add_field(name="Letzte Transaktionen", value=log_text, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── ADMIN: ALIAS LOOKUP ──────────────────────────────────────────────────────
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

# ─── SETUP ────────────────────────────────────────────────────────────────────
@tree.command(name="setup", description="[ADMIN] Server einrichten")
async def setup(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("❌ Kein Zugriff.", ephemeral=True)
        return

    await interaction.response.send_message("⚙️ Richte Server ein...", ephemeral=True)
    guild = interaction.guild

    # Alle bestehenden Channels löschen
    for channel in guild.channels:
        try:
            await channel.delete()
        except:
            pass

    # @everyone keine Rechte
    await guild.default_role.edit(permissions=discord.Permissions.none())

    # Rollen erstellen
    mitglied_rolle = await guild.create_role(
        name="Mitglied",
        color=discord.Color.dark_red()
    )
    admin_rolle = await guild.create_role(
        name="Admin",
        color=discord.Color.gold(),
        permissions=discord.Permissions.all()
    )

    # Permissions
    everyone = guild.default_role
    deny_all = discord.PermissionOverwrite(read_messages=False, send_messages=False)
    member_rw = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    member_ro = discord.PermissionOverwrite(read_messages=True, send_messages=False)
    admin_rw  = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

    # Kategorien & Channels
    cat_markt = await guild.create_category("🕶️ UNTERGRUND", overwrites={
        everyone: deny_all,
        mitglied_rolle: discord.PermissionOverwrite(read_messages=True)
    })

    schwarzmarkt_ch = await guild.create_text_channel("schwarzmarkt", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Illegale Waren & Angebote")

    auftraege_ch = await guild.create_text_channel("auftraege", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Anonyme Aufträge")

    kopfgelder_ch = await guild.create_text_channel("kopfgelder", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_ro, admin_rolle: admin_rw
    }, topic="Aktive Kopfgelder")

    befehle_ch = await guild.create_text_channel("befehle", category=cat_markt, overwrites={
        everyone: deny_all, mitglied_rolle: member_rw, admin_rolle: admin_rw
    }, topic="Hier Commands eingeben")

    cat_admin = await guild.create_category("🔒 ADMIN", overwrites={
        everyone: deny_all, mitglied_rolle: deny_all, admin_rolle: admin_rw
    })

    log_ch = await guild.create_text_channel("admin-log", category=cat_admin, overwrites={
        everyone: deny_all, mitglied_rolle: deny_all, admin_rolle: admin_rw
    })

    # Admin Rolle dem Owner geben
    await guild.owner.add_roles(admin_rolle)

    # Channel IDs global setzen
    global CH_SCHWARZMARKT, CH_AUFTRAEGE, CH_KOPFGELDER, CH_LOG
    CH_SCHWARZMARKT = schwarzmarkt_ch.id
    CH_AUFTRAEGE    = auftraege_ch.id
    CH_KOPFGELDER   = kopfgelder_ch.id
    CH_LOG          = log_ch.id

    result = f"""✅ **Server eingerichtet!**

**Füge diese IDs in deinen Code ein damit sie nach Neustart erhalten bleiben:**
```
CH_SCHWARZMARKT = {schwarzmarkt_ch.id}
CH_AUFTRAEGE    = {auftraege_ch.id}
CH_KOPFGELDER   = {kopfgelder_ch.id}
CH_LOG          = {log_ch.id}
```"""

    await log_ch.send(result)


bot.run(TOKEN)
