English readme at the bottom.

Ich bin ein Chatbot und benachrichtige dich über neue Angebote auf [wg-gesucht.de]() in Berlin, Hamburg, München,
Frankfurt, Köln und Stuttgart. Für andere Städte: siehe Ende. 

Ich spreche über Telegram zu dir. Das ist ein Messenger  wie Whatsapp den du im Browser, am Handy oder auf dem PC
benutzen kannst. Du findest ihn auf [t.me]() und diesen Bot unter [t.me/wg_ges_bot]() oder such einfach @wg_ges_bot in
der App.

Ich freue mich sehr über Feedback, gefundene Fehler, stolze Berichte vom WG-Fund, Liebesbekundungen, Beleidigungen an 
[wg-ges-bot@web.de]().

Hättest du diesen Bot gerne für eine **andere Stadt**, dann schreib mir einfach. Ich helfe dir gerne mit der kleinen 
Anpassung des Codes. Laufen lassen musst du ihn vermutlich selbst. Dazu reicht z.B. ein Raspberry Pi bei dir 
daheim.  
Jemand hat den Bot angepasst und sucht für euch in Karlsruhe, Freiburg, Heidelberg, Stuttgart, Konstanz und 
Mannheim. Ihr findet ihn auf Telegram unter @wg_gesucht_ka_bot oder [t.me/wg_gesucht_ka_bot]().

Ich bin NICHT von [wg-gesucht.de](), sondern ein Privatprojekt. Ich verdiene nichts mit diesem Service und habe das auch
nicht vor. Ich möchte weder der Seite noch euch oder Anderen Schaden zufügen. Ich speichere weder eure Daten, noch die
der Website und gebe auch keine Daten an Dritte weiter.

English:
- 
I'm a chatbot notifying you about new offers from [wg-gesucht.de](). You'll need Telegram (a messenger just like 
Whatsapp) to use me. Get it on [t.me]() and find me via [t.me/wg_ges_bot]() or searching @wg_ges_bot in the Telegram App.

Please send feedback, bugs, love letters to [wg-ges-bot@web.de](). If you need this bot for some other city, just contact
me. I'll help you with the small code changes, but you'll need to run it yourself (a raspberry pi would be enough).

Disclaimer:  
I'm not connected to [wg-gesucht.de](). I don't save any of your data or give it to others. I don't make any money with 
this, nor do i plan to ever do so. I don't intend to inflict any damage to you, [wg-gesucht.de]() or others.

Installation:
-
- install tor [https://www.torproject.org/docs/]() and set up the controlport 9051 and a password. This might help: 
[https://stackoverflow.com/questions/30286293/make-requests-using-python-over-tor]()
- get Telegram at [https://t.me]() and speak to the Botfather to get your Bot Token.
- create a params.py file and populate it according to params_template.py
- install the required python packages
- run wg_ges_bot_tor_6_cities.py
- write the Bot "/scrape_begin" from an admin account
- Edit the URLs (or whatever else) to your liking
- If you run this for a different set of cities please let me know so I can link you here

Thank you [https://github.com/python-telegram-bot/python-telegram-bot]() for the great wrapper (that i couldn't refuse).