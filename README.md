# Personal-FeedRSS

Aggrega feed pubblici su security advisory e CVE e su GDPR e data privacy, e li pubblica come feed RSS su GitHub Pages. Si aggiorna ogni 30 minuti con GitHub Actions.

## Feed generati

- `feed.xml`: tutte le fonti
- `security.xml`: solo security advisory e CVE
- `privacy.xml`: solo GDPR e data privacy
- `index.html`: link ai feed e stato di ogni fonte

L'indirizzo sarà `https://bubbles10.github.io/Personal-FeedRSS/feed.xml`.

## Attivazione

1. Carica questi file nel repository, sul branch `main`.
2. Su GitHub apri Settings > Pages e in "Build and deployment" scegli **GitHub Actions** come Source.
3. Apri la scheda Actions, seleziona "Aggiorna feed" e premi **Run workflow** per la prima pubblicazione.
4. Aggiungi l'URL di `feed.xml` alla tua app RSS.

## Aggiungere o togliere fonti

Modifica `sources.yml`. Per ogni fonte puoi impostare:
- `max_items`: quante voci tenere al massimo da quella fonte;
- `include`: una lista di parole chiave; restano solo le voci che ne contengono almeno una.

Il feed tiene le voci degli ultimi 14 giorni, al massimo 300, ed elimina i doppioni con lo stesso link.

## Prova in locale

```
pip install -r requirements.txt
python aggregate.py --out public
```

Se nessuna fonte risponde, lo script esce con errore e il feed già pubblicato non viene sovrascritto.

## Note

- GitHub Actions può ritardare o saltare le esecuzioni pianificate quando è sotto carico, e le sospende dopo 60 giorni senza attività nel repository.
- Su un account gratuito GitHub Pages funziona solo con repository pubblici. Il feed contiene solo notizie pubbliche.
