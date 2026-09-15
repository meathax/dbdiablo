# Diablo and Hellfire for MiSTer

This database installs the MiSTer runtime and DevilutionX language assets. It does not store the retail Diablo or Hellfire archives in Git; Downloader_MiSTer fetches those from the URLs in `external_files.csv`.

Add this database to `downloader.ini`:

```ini
[meathax/dbdiablo]
db_url = https://raw.githubusercontent.com/meathax/dbdiablo/db/db.json.zip
```

Run **Update All** in Downloader_MiSTer. The external-file list installs the retail and Hellfire archives, language files, and shareware data into `/media/fat/games/Diablo/`.

The required retail and Hellfire archives are:

- `DIABDAT.MPQ`
- `hellfire.mpq`
- `hfmonk.mpq`
- `hfmusic.mpq`
- `hfvoice.mpq`

Language and shareware archives installed beside them are:

- `devilutionx.mpq` for DevilutionX translated UI and text assets.
- `fonts.mpq` for additional Chinese, Japanese, and Korean fonts.
- `es.mpq`, `pl.mpq`, and `ru.mpq` for language-specific content and voice support.
- `spawn.mpq` for the Diablo shareware data.

The installed runtime consists of:

- `/media/fat/Diablo`
- `/media/fat/_Other/Diablo.rbf`
- `/media/fat/_Other/Hellfire.rbf`
- `/media/fat/_Other/Diablo/`

Launch Diablo or Diablo Hellfire from the MiSTer `_Other` menu. Configuration and saves are kept in `/media/fat/saves/Diablo/`.

Development source: [meathax/diablo](https://github.com/meathax/diablo).
