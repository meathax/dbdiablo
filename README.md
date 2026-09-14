# Diablo and Hellfire for MiSTer

This database installs the complete redistributable MiSTer runtime for the Diablo core. It does not contain the retail game archives.

Add this database to `downloader.ini`:

```ini
[meathax/dbdiablo]
db_url = https://raw.githubusercontent.com/meathax/dbdiablo/db/db.json.zip
```

Run **Update All** in Downloader_MiSTer. The external-file list downloads the base Diablo archive and all required Hellfire archives to `/media/fat/games/Diablo/`:

- `DIABDAT.MPQ`
- `hellfire.mpq`
- `hfmonk.mpq`
- `hfmusic.mpq`
- `hfvoice.mpq`

The installed runtime consists of:

- `/media/fat/Diablo`
- `/media/fat/_Other/Diablo.rbf`
- `/media/fat/_Other/Hellfire.rbf`
- `/media/fat/_Other/Diablo/`

Launch Diablo or Diablo Hellfire from the MiSTer `_Other` menu. Configuration and saves are kept in `/media/fat/saves/Diablo/`.

Development source: [meathax/diablo](https://github.com/meathax/diablo).
