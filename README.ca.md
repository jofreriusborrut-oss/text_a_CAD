# Text a CAD

*[English version](README.md)*

Descriu una peça mecànica amb text, amb les mesures en mil·límetres, i obtén un
model 3D paramètric que pots veure, ajustar amb controls lliscants i descarregar
en **STEP** (per a SolidWorks, Fusion, FreeCAD…) i **STL** (per imprimir en 3D).

Claude escriu el codi [CadQuery](https://cadquery.readthedocs.io). L'app
l'executa en un procés separat, comprova el resultat i el mostra en un visor 3D
interactiu.

![Text a CAD](docs/captures/app.png)

## Què fa

- **Text → model 3D**: per exemple, *«Placa de 60x80x5 mm amb 4 forats de 6,5 mm
  a 10 mm de les vores i cantonades arrodonides de radi 4»*.
- **Autocorrecció**: si el codi falla, l'error torna a Claude perquè el
  corregeixi (fins a 3 intents). L'app mostra en quin intent es troba.
- **Visor 3D interactiu** (three.js, funciona sense internet): girar, desplaçar,
  zoom i vistes isomètrica, superior, frontal i lateral.
- **Descàrrega en STEP i STL**, i el codi generat en una secció plegable.
- **Un control lliscant per a cada mesura**: totes les mesures són en un
  diccionari `PARAMS`. Quan mous un control, la peça es regenera a l'ordinador
  **sense tornar a cridar Claude**.
- **Comprovacions automàtiques**:
  - sòlid vàlid i tancat;
  - la mida total (bounding box) coincideix amb la descripció;
  - parets de menys d'1,2 mm (risc en impressió 3D);
  - volum i pes aproximat en PLA.
- **Historial de la sessió**: pots tornar a qualsevol peça generada.

## Requisits

- **Python 3.12** (Windows, macOS o Linux).
- Una d'aquestes maneres de connectar amb Claude:
  - **Claude Code** amb una subscripció Claude Pro/Max (per defecte, sense cost
    d'API): l'app executa `claude -p`. Instal·la'l seguint
    [la guia oficial](https://code.claude.com/docs/en/setup), després executa
    `claude` una vegada al terminal i inicia la sessió.
  - O bé una **clau de l'API d'Anthropic** (es paga per ús).

## Instal·lació (Windows)

Obre *PowerShell* (o el terminal de VS Code) a la carpeta on guardes els projectes:

```bash
git clone https://github.com/jofreriusborrut-oss/text_a_CAD.git
```
```bash
cd text_a_CAD
```
```bash
py -3.12 -m venv .venv
```
```bash
.venv\Scripts\activate
```
```bash
pip install -r requirements.txt
```
```bash
copy .env.example .env
```

A macOS/Linux fes servir `python3.12 -m venv .venv`, `source .venv/bin/activate`
i `cp .env.example .env`.

Instal·lar CadQuery baixa uns 300 MB i pot trigar uns minuts.

## Configuració (`.env`)

El fitxer `.env` conté la teva configuració i **no es puja mai a git**
(és a `.gitignore`).

| Variable | Per defecte | Significat |
|---|---|---|
| `CLAUDE_BACKEND` | `cli` | `cli` = `claude -p` (subscripció) · `api` = API d'Anthropic |
| `CLAUDE_MODEL` | `claude-sonnet-5-5` | Model que escriu el codi |
| `ANTHROPIC_API_KEY` | *(buit)* | Només per a `CLAUDE_BACKEND=api` |
| `CLAUDE_CLI_PATH` | *(buit)* | Ruta completa de `claude` si no és al PATH |
| `EXEC_TIMEOUT` | `30` | Segons màxims per executar el codi CadQuery |
| `CLAUDE_TIMEOUT` | `180` | Segons màxims per a cada resposta de Claude |

Amb `CLAUDE_BACKEND=cli`, l'app treu `ANTHROPIC_API_KEY` de l'entorn de
`claude -p`, perquè sempre faci servir la teva subscripció.

## Com es fa servir

### Aplicació web

```bash
streamlit run app.py
```

S'obre el navegador a `http://localhost:8501`.

1. Escriu la descripció de la peça. Sigues precís: mida total, gruixos, forats
   (diàmetre **i** posició), arrodoniments i xamfrans.
2. Prem **Genera la peça** i segueix els intents.
3. Mira la peça, llegeix les comprovacions, mou els controls i descarrega
   l'STEP o l'STL.
4. Obre l'STEP a SolidWorks (*Fitxer → Obrir*, tipus *STEP*).

<!-- Captura: generant una peça (intent 1/3, 2/3…) -->
<!-- ![Generació](docs/captures/generacio.png) -->

<!-- Captura: controls lliscants -->
<!-- ![Controls](docs/captures/controls.png) -->

<!-- Captura: l'STEP obert a SolidWorks -->
<!-- ![SolidWorks](docs/captures/solidworks.png) -->

### Terminal

```bash
python cli.py "Placa de 60x80x5 mm amb 4 forats de 6,5 mm a 10 mm de les vores"
```

L'STEP, l'STL i el codi es guarden a `sortida/<nom>/`. També pots executar un
fitxer CadQuery sense Claude:

```bash
python cli.py --code tests/parts/a_placa.py
```

## Com escriure bones descripcions

- Dona la mida total com a `llargada x amplada x alçada` (X × Y × Z).
- Per als forats, dona el diàmetre i la posició: *«4 forats de 6,5 mm a 10 mm de
  les vores»*, o la mètrica del cargol: *«3 forats M6»* (forats de pas: M3 3,4,
  M4 4,5, M5 5,5, M6 6,6 mm).
- Digues quines arestes van arrodonides o amb xamfrà.
- Si falta alguna dada, Claude tria un valor raonable i n'hi afegeix el control.

## Tests

Tests que **no** criden Claude (codi CadQuery escrit a mà i un `claude` fals):

```bash
pytest
```

Tests reals: les 5 descripcions de referència de `tests/descripcions.py` s'envien
a Claude, i totes han de donar una peça vàlida. Els resultats es guarden a
`sortida/tests/` perquè els puguis obrir amb SolidWorks.

```bash
$env:RUN_CLAUDE_TESTS=1; pytest tests/test_generacio.py -v
```

(A macOS/Linux: `RUN_CLAUDE_TESTS=1 pytest tests/test_generacio.py -v`.)

## Com funciona

```
descripció ──► Claude (claude -p o API) ──► codi CadQuery amb PARAMS
                    ▲                               │
                    │ error + codi (màx. 3 intents) ▼
                    └────────────── runner.py en un procés separat (30 s)
                                                    │
                    STEP + STL + mesures ◄──────────┘
                               │
        visor · descàrregues · comprovacions · controls (reescriuen PARAMS i
                                                         tornen a executar)
```

El codi generat sempre té la mateixa estructura:

```python
import cadquery as cq

PARAMS = {
    "length": {"value": 60, "unit": "mm", "min": 30, "max": 200, "label": "Llargada (X)"},
    # ... una entrada per a cada mesura
}

L = PARAMS["length"]["value"]
# ... geometria construïda només a partir de PARAMS ...
result = ...                       # el sòlid
EXPECTED_BBOX = (L, W, T)          # mida total esperada segons la descripció
```

| Fitxer | Què fa |
|---|---|
| `app.py` | Interfície Streamlit |
| `cli.py` | Interfície de terminal |
| `textacad/prompts.py` | Prompt de sistema amb les regles i 4 exemples provats |
| `textacad/generator.py` | Parla amb Claude i fa el bucle de correcció |
| `textacad/sandbox.py`, `runner.py` | Executen el codi en un procés separat amb límit de temps |
| `textacad/params.py` | Llegeix i reescriu `PARAMS` (amb el mòdul `ast` de Python) |
| `textacad/regenerate.py` | Regenera la peça amb els valors dels controls |
| `textacad/checks.py` | Comprovacions automàtiques |
| `textacad/viewer.py` | Visor 3D amb three.js |

**Nota de seguretat:** el codi generat s'executa al teu ordinador, en un procés
separat i amb límit de temps. Això protegeix l'app de penjades i bucles
infinits, però no és un aïllament complet. El prompt prohibeix accedir a fitxers
i a la xarxa, però tracta el codi com qualsevol script que baixes d'internet.

## Problemes habituals

- **`The claude command was not found`**: instal·la Claude Code i executa
  `claude` una vegada per iniciar la sessió. Si no, posa `CLAUDE_CLI_PATH` al
  `.env` (per exemple `C:\Users\<tu>\AppData\Roaming\npm\claude.cmd`) o fes
  servir `CLAUDE_BACKEND=api`.
- **La primera peça triga molt**: la primera vegada, Python carrega OpenCascade
  (i Windows Defender l'analitza). Aquesta càrrega no compta dins el límit
  de 30 s.
- **«Aquesta combinació de valors no genera una peça vàlida»**: algunes
  combinacions de controls són impossibles (per exemple, forats més grans que la
  placa). Es manté l'última peça vàlida.

## Llicència

[MIT](LICENSE) © 2026 Jofre Rius Borrut. three.js (MIT) està inclòs a
`textacad/static/three`.
