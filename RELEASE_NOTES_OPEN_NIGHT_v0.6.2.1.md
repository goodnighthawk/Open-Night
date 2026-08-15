# Open Night v0.6.2.1

- Built directly over v0.6.2 and therefore over the full v0.6.1 polished-map release.
- Fixed `DEPLOY_OPEN_NIGHT_SERVER.bat` closing after its first Railway command.
- Railway's npm installation provides `railway.cmd`; every invocation now uses `call railway.cmd ...`, ensuring Windows returns control to the parent deployment script.
- All completion and failure paths now return through one final handler that shows the exit code and pauses before closing.
- Automatic Railway server discovery and all v0.6.1 map/gameplay features are unchanged.
