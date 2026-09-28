FotoSorter
==========

Sorts vacation photos: filters out blurry/dark ones, finds near-duplicate
bursts so you can pick the best, and files everything by year and country.


INSTALL
-------

1. Open a terminal in this folder.
2. Create a virtual environment:
       python3 -m venv .venv
3. Install dependencies into it:
       ./.venv/bin/pip install -r requirements.txt

Do this once. You don't need to repeat it unless requirements.txt changes.


ADDING PHOTOS
-------------

Copy your photos into the RAW/ folder (subfolders are fine). Supported
formats: JPG, PNG, HEIC, HEIF.


RUNNING
-------

    ./.venv/bin/python main.py

Run this every time you want to sort new photos or continue reviewing.


FIRST RUN
---------

1. The app scans RAW/ and analyzes every new photo. A progress bar shows
   what it's doing.
2. If a photo's date isn't covered by a location rule yet, a window pops
   up asking you to name it: pick a start date, an end date, and type a
   place name (e.g. "USA"). Click "Add rule", then "OK".
3. Photos with no near-duplicates are saved automatically.
4. For photos that look similar to each other (a "burst"), you get a
   review screen showing all of them at once:
     - Left-click a photo to zoom in, right-click to zoom out.
     - The photo with a yellow border is the suggested sharpest one.
     - Tick "Keep this one" under every photo you want to keep - more
       than one is fine.
     - Click "Save & Next" to file your choices and move to the next
       group.
5. When there's nothing left to review, it says so.

You can close the app any time - it remembers where you left off.


WHERE YOUR PHOTOS END UP
-------------------------

    DATA/<year>/lowQuality/              blurry or badly lit photos
    DATA/<year>/<place>/SAVED/           photos you kept
    DATA/<year>/<place>/DISCARDED/       duplicates you didn't keep

Nothing is ever deleted - only moved.


TOOLBAR BUTTONS
----------------

  Re-scan RAW/                     Check for new photos without restarting.
  Location rules...                Add/edit the date -> place mappings.
  Settings...                      Tune how strict blur/duplicate detection is.
  Compress folder...                Make small copies of photos to save
                                    space (originals are never touched).
  Re-check lowQuality...           Re-judge lowQuality photos after
                                    changing Settings.
  Compare original/compressed...   View a photo next to its compressed
                                    copy to check quality.
  Browse lowQuality...             Scroll through lowQuality photos one by
                                    one and manually save the ones worth
                                    keeping.


MORE DETAIL
-----------

See DEV_README.txt for how it works internally.
