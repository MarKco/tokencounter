# TokenCounter

TUI a colori per tracciare nel tempo il consumo di token — in percentuale o in $ — con grafico a linee o a barre, tendenza proiettata e ciclo di reset mensile.

## Requisiti

- Python 3.9+
- `pipx` (consigliato per l'installazione):
  - macOS: `brew install pipx`
  - Debian/Ubuntu: `sudo apt install pipx`
  - altrimenti: `python3 -m pip install --user pipx`

## Installazione

### Opzione A — da sorgente (più semplice)

Copia o clona la cartella `tokencounter/` sulla macchina di destinazione, poi:

```bash
cd tokencounter
pipx install .
```

`pipx` crea un ambiente isolato, installa le dipendenze (`textual`, `textual-plotext`) ed espone il comando `tokencounter` nel PATH.

### Opzione B — pacchetto distribuibile (un solo file)

Sulla macchina dove hai i sorgenti:

```bash
cd tokencounter
python3 -m pip install --user build
python3 -m build
```

Questo genera `dist/tokencounter-<versione>-py3-none-any.whl` (la versione è quella in `pyproject.toml`). Copia solo quel file sulla macchina di destinazione e installa con:

```bash
pipx install tokencounter-<versione>-py3-none-any.whl
```

### Aggiornamento

Se hai i sorgenti aggiornati (es. dopo `git pull`), dalla cartella `tokencounter/`:

```bash
cd tokencounter
pipx install . --force
```

`--force` reinstalla sovrascrivendo la versione precedente. I dati salvati (vedi sotto) non vengono toccati.

Per verificare la versione installata:

```bash
pipx list
```

oppure, a programma avviato, il numero versione è mostrato nel sottotitolo della finestra.

### Disinstallazione

```bash
pipx uninstall tokencounter
```

I dati salvati (vedi sotto) non vengono rimossi automaticamente.

## Avvio

```bash
tokencounter
```

## Uso

Il programma apre una schermata a schermo intero con:

- **grafico** in alto (linee o barre)
- **barra di stato** con giorno di reset, ciclo corrente, giorni rimanenti (colorati verde/giallo/rosso), ultimo valore inserito, valore massimo che puoi inserire oggi senza far sforare la tendenza a fine ciclo, tipo di grafico, ed eventuale avviso di rischio esaurimento
- **campo di input** in basso, per inserire i valori
- **footer** con il riepilogo dei tasti

### Modalita' % o $

Il programma puo' ragionare in due modalita', indipendenti tra loro (ciascuna ha la propria serie di valori salvata separatamente):

- **%** (default): inserisci la percentuale di token consumati finora nel ciclo (0-100)
- **$**: inserisci quanti $ hai consumato finora nel ciclo, con tutti i decimali che vuoi (utile quando la percentuale non e' abbastanza precisa). Il "pieno" non e' 100 ma un **plafond** in $ che imposti tu (default 500), e che si resets col ciclo esattamente come il 100%

`Ctrl+M` alterna tra le due modalita'. `Ctrl+B` apre una finestra per cambiare il plafond in $. Passare da una modalita' all'altra e' solo un cambio di vista: i valori dell'altra modalita' restano intatti e li ritrovi tali e quali tornando indietro.

### Inserire un valore

Digita un numero nel campo in basso (percentuale 0-100, oppure $ consumati a seconda della modalita' attiva) e premi **Invio**. Il valore rappresenta sempre il totale consumato finora nel ciclo, non l'incremento dall'ultima voce. Il punto viene aggiunto con la data/ora corrente e il grafico si aggiorna subito.

### Tasti

| Tasto                          | Azione                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------ |
| `Invio` (nel campo di input) | Aggiunge il valore digitato                                                          |
| `q`                          | Esce dal programma (funziona anche mentre il campo di input è attivo)               |
| `Ctrl+R`                     | Modifica giorno di reset (giorno del mese in cui i token si resettano)               |
| `Ctrl+X`                     | Azzera tutti i valori inseriti (richiede conferma)                                   |
| `T`                          | Alterna il grafico tra linee e barre                                                 |
| `Ctrl+D`                     | Attiva/disattiva la modalita' demo                                                   |
| `Ctrl+M`                     | Alterna tra modalita' % e modalita' $                                                |
| `Ctrl+B`                     | Apre la finestra per cambiare il plafond in $                                        |
| `Ctrl+L`                     | Apre la lista dei valori inseriti (modalita' corrente), per modificarli o eliminarli |
| `?`                          | Info: come vengono calcolati tendenza e intervallo di confidenza                     |

### Grafico a linee

- Linea ciano con punti = valori inseriti, interpolati
- Linea gialla = retta di tendenza, calcolata per regressione lineare pesata sugli ultimi 14 giorni di valori inseriti: i punti più recenti pesano di più (si dimezzano ogni 7 giorni) e un valore anomalo isolato (es. inserito per errore) viene automaticamente scartato dal calcolo
- Linea arancione = "budget ideale", cioè l'andamento lineare da 0 al "pieno" (100% oppure il plafond in $) dall'inizio alla fine del ciclo corrente, utile per capire a colpo d'occhio se si sta consumando più o meno del previsto
- Segmento magenta verticale a fine ciclo = intervallo di confidenza (~90%) sul valore finale previsto: più i valori inseriti sono irregolari, più è ampio. Non compare se non ci sono abbastanza dati per stimarlo

Sotto la legenda, nell'area in alto a sinistra (di solito libera perché a inizio ciclo si parte da zero), il grafico mostra anche in cifre il **pace ideale** (target diviso i giorni del ciclo, cioè la pendenza della linea arancione) e, se ci sono almeno due valori, il **rate** più recente (la pendenza della linea gialla, cioè quanto stai consumando al giorno secondo la tendenza pesata).

Il grafico mostra sempre e solo il ciclo corrente (dal giorno di reset a quello successivo): i valori inseriti nei cicli precedenti restano salvati ma non compaiono più una volta chiuso il ciclo. Cambiare il giorno di reset (`Ctrl+R`) non cancella né mescola dati: serve solo a spostare "dove sei" all'interno del mese.

### "Max oggi senza sforare"

Nella barra di stato viene mostrato il valore massimo che puoi inserire adesso senza che la retta di tendenza (ricalcolata includendo questo nuovo valore) superi il "pieno" (100% oppure il plafond in $) entro la fine del ciclo. Se il valore è già oltre la tendenza attuale, o se non ci sono ancora abbastanza dati, viene mostrato un messaggio invece di un numero.

### Grafico a barre

- Una barra ciano per ogni valore realmente inserito
- Linea gialla di tendenza sovrapposta alle barre (stessa retta di regressione del grafico a linee)
- Resta presente la linea arancione di budget ideale

### Cambiare il giorno di reset

`Ctrl+R` apre una finestra modale: inserisci il giorno del mese (1-31) e premi Invio. `Esc` annulla senza modificare nulla.

### Azzerare i dati

`Ctrl+X` apre una finestra di conferma. Selezionando "Sì, azzera" vengono cancellati i valori della **sola modalità attiva** (% oppure $ — l'altra serie non viene toccata). Giorno di reset e plafond restano invariati. `Esc` o "Annulla" chiudono senza cancellare nulla.

### Vedere e modificare i valori inseriti

`Ctrl+L` apre la lista di tutti i valori inseriti nella modalità attiva (data/ora e valore), utile se ti accorgi di aver sbagliato qualcosa. Dentro la lista:

- Frecce su/giù per spostarti tra le voci
- `e` modifica il valore della voce selezionata (si apre un campo con il valore attuale precompilato, pronto per essere sovrascritto)
- `d` elimina la voce selezionata (richiede conferma)
- `Esc` chiude la lista e torna al grafico, aggiornato con le eventuali modifiche

## Modalita' demo

`Ctrl+D` avvia una demo con dati simulati: un punto ogni 5 secondi, distribuiti su un ciclo fittizio di ~28 giorni, con un andamento che parte piano, poi accelera abbastanza da far uscire la retta di tendenza dal budget (si vede comparire l'avviso di rischio esaurimento), poi rallenta e scende. Serve per vedere a colpo d'occhio come si comporta il grafico in uno scenario reale.

La demo non tocca mai i dati reali salvati: mentre e' attiva lo vedi dall'etichetta **DEMO** e dal contatore di avanzamento nella barra di stato. Premendo di nuovo `Ctrl+D` torni immediatamente ai tuoi dati, esattamente come li avevi lasciati.

## Persistenza dei dati

Tutto (valori inseriti in entrambe le modalità, giorno di reset, tipo di grafico, modalità attiva e plafond in $) viene salvato in:

```
~/.config/tokencounter/data.json
```

Chiudendo e riaprendo il programma, i dati vengono ricaricati automaticamente da questo file.
