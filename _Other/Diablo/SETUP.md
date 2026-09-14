# Diablo MiSTer package setup

1. Copy this package to a clean MiSTer SD-card directory without changing any
   file names or manifest contents.
2. Supply your own legally obtained Diablo or Hellfire data directory. Licensed
   MPQ files and save/configuration data are deliberately outside this package.
3. Verify `package-manifest.json` and `deployment.json` before activation.
4. After transactional installation has created `/media/fat/.diablo-install.json`,
   copy `Diablo.sh` and `Hellfire.sh` to `/media/fat/Scripts/`. Select either entry
   from the MiSTer Scripts menu. They follow the active installation, including
    updates and rollback, and run the package launcher with Python 3.
    Default game data: `/media/fat/games/Diablo`; saves: `/media/fat/saves/Diablo`;
    configuration: `/media/fat/config/Diablo`. The launcher separates campaigns.
    Complete packages include the redistributable Hellfire `hf.mpq` mod in the
    asset tree; the launcher stages the archive into the save root. Matching
    legacy loose mod files are backed up beside the save directory.
   For another layout, export DIABLO_INSTALL_ROOT, DIABLO_DATA_ROOT,
   DIABLO_SAVE_ROOT or DIABLO_CONFIG_ROOT before invoking the script.
   Keep MPQs outside managed releases. Python 3 must be available on PATH.
5. Keep the previous package available until an update has completed a second
   launch and save/load smoke check. If an update is interrupted, leave the
   active release selected and retry from a fresh staging directory.

The package does not claim physical video, audio, input, gameplay, performance,
or release acceptance by itself; those claims require the qualification receipts
listed in the completion plan.
