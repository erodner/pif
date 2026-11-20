Prompt Injection Finder
=======================

1. Drag "Prompt Injection Finder.app" into your Applications folder.

2. The app is not signed with an Apple Developer ID, so macOS blocks it the first time:
   - Double-click the app. macOS says it cannot be verified. Click "Done" (or "Cancel").
   - Open System Settings > Privacy & Security, scroll down and click "Open Anyway".
   - Confirm once more. From then on the app opens normally.

   Alternative (Terminal):
       xattr -dr com.apple.quarantine "/Applications/Prompt Injection Finder.app"

3. The command line tool is inside the app:
       "/Applications/Prompt Injection Finder.app/Contents/MacOS/pif" scan ~/Papers -f html -o report.html

Free software under the GNU AGPL v3 or later. Source: https://github.com/erodner/pif
