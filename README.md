# Scrapper for IURA


## STEPS
 - Create a Virtual Environment
 - Run the installation: `pip install -r requirements.txt`

 - Add the .env file
 
 - Run this in the bash terminal
  ` "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --use `
 The Edge Browser will open up, on that search and go to the relevent site.

 - Open another terminal, and run this command from the repository root.
   `python app/scrapper.py --start 1947 --end 2025`
  --start defines the starting year.
  --end defines the ending year.
   This will attach the scrapper to the browser.

- Make sure to move the cursor, and click on some random areas, to avoid low reCaptcha scores.
