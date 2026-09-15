# Diablo and Hellfire data

Downloader_MiSTer installs the files listed in the repository's `external_files.csv` into this directory. The required retail and Hellfire archives are:

- `DIABDAT.MPQ` for the full base game
- `hellfire.mpq`, `hfmonk.mpq`, `hfmusic.mpq`, and `hfvoice.mpq` for Hellfire

The language and shareware archives are:

- `devilutionx.mpq` for DevilutionX translated UI and text assets
- `fonts.mpq` for additional Chinese, Japanese, and Korean fonts
- `es.mpq`, `pl.mpq`, and `ru.mpq` for language-specific content and voice support
- `spawn.mpq` for the Diablo shareware data; DevilutionX can use it instead of `DIABDAT.MPQ` for the shareware portion

The standard database install includes `DIABDAT.MPQ`, so the full retail archive takes precedence when both base-game archives are present. Configuration and saved games are stored separately in `/media/fat/saves/Diablo/`.
