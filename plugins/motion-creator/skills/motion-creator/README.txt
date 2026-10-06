Motion Creator: an animation studio for Claude
==============================================

What is it?
A skill that turns Claude into an animation studio. You ask for an animation, pick one of 10 styles
(or describe your own), approve the scene list, and Claude builds the animation in code,
reviews it itself and exports an MP4 file, and a GIF if you want one.
All on-screen text is in Hebrew, right to left.

What do you need?
* Claude Code or Cowork.
* Claude Opus 5.5 or later. With a weaker model the motion comes out stiff.
* The first time, Claude installs the tools it needs on its own (Python, a browser that captures
  the frames, and ffmpeg). You only approve. It takes a few minutes, once.

How to install?
1. Unzip the file (right click > Extract All / Open).
2. Open Claude Code and tell it:
   Install the skill from this folder: <path to the motion-creator folder>
3. Close and reopen Claude Code.

Using Cowork? On claude.ai go to Settings > Skills and upload the zip file.

Want to install manually? Copy the motion-creator folder into your skills folder:
   Mac:      /Users/<username>/.claude/skills
   Windows:  C:\Users\<username>\.claude\skills
   (if the skills folder doesn't exist, create it)

How to use it?
Tell Claude "make me an animation". It will ask which style, ask a few questions about the
text and colours, show you the plan, and only after you approve will it start building.

Music
The skill doesn't come with songs. Want music? Download a song from Mixkit (mixkit.co,
free even for commercial use) and give Claude the file. Without a song, Claude generates
sound effects itself.

The fonts in the folder are Google Fonts under the OFL license. Details in assets/fonts/OFL.txt.
