# <img src="kerfly/gui/icons/kerfly.svg" width="48" alt="" align="center"> Kerfly

[![tests](https://github.com/cyryllo/Kerfly/actions/workflows/tests.yml/badge.svg)](https://github.com/cyryllo/Kerfly/actions/workflows/tests.yml)

**Strona i instrukcja obsługi:** [cyryllo.github.io/Kerfly/pl](https://cyryllo.github.io/Kerfly/pl/) · **English:** [README.md](README.md)

Kerfly to program do sterowania laserami CO2 klasy K40 z płytami Lihuiyu
(rodzina M2 Nano). Działa na Linuksie (przede wszystkim Debian) i Windows.

Kerfly powstał z **[K40 Whisperer](https://www.scorchworks.com/K40whisperer/k40whisperer.html)**
autorstwa Scorcha (scorchworks.com), w wersji 0.71, znanej ze stabilnego
sterowania laserem. Oryginalne wydanie ma w tym repozytorium tag
`upstream-0.71`.

![Główne okno Kerfly](docs/screenshot_pl.png)

## Stan projektu

Wczesna faza rozwoju (0.16). Pierwszy test na prawdziwym K40 (Windows 10,
płyta M3) odbył się w listopadzie 2026, a poprawki po nim weszły do wersji
0.15.0. Kerfly ma nowe okno w Qt (PySide6). Otwiera pliki SVG, DXF i G-code
oraz obrazy (PNG, JPG, BMP, TIFF, GIF, WebP) do grawerowania rastrowego, bez
Inkscape.

Narzędzia rysowania są na pasku po prawej stronie stołu, jak w LightBurnie:
prostokąt (także z zaokrąglonymi rogami), elipsa, wielokąt foremny, linia,
łamana, pióro (krzywe), rysowanie odręczne i tekst dowolną zainstalowaną
czcionką. Każdy kształt można wyciąć, wygrawerować jako obrys, wypełnić liniami
(kreskowanie) albo wygrawerować rastrowo. Narzędzie **Wypełnienie** (wiaderko)
wypełnia zamknięte kształty grawerowanymi wzorami (linie, fale, plaster miodu,
cegły…), a ich obrys nadal jest cięty, a tekst można ułożyć na ścieżce (linii,
krzywej albo okręgu). Pozycja, rozmiar i obrót
zaznaczonego elementu oraz opcje kształtu lub narzędzia (warstwa, promień
rogów, tekst, czcionka) są na pasku nad stołem.

Praca jest podzielona na warstwy, jak w LightBurnie. Warstwa to grawer
rastrowy (**Grawer**), grawer wektorowy (**Obrys**) albo cięcie (**Cięcie**),
każda z własną prędkością, liczbą przejść, mocą (płyty M3) i kolorem. Części
każdego elementu można przypisać do dowolnej warstwy pasującego rodzaju. Baza
materiałów (np. „Sklejka 3 mm”) zapamiętuje ustawienia cięcia, obrysu i
graweru i ustawia wszystkie warstwy jednym wyborem.

Projekt (**Plik → Zapisz projekt**, plik `.kerfly`) zawiera układ, warstwy,
narysowane kształty i kopie plików źródłowych w jednym pliku, więc łatwo go
przenieść na komputer przy laserze.

Projekty układa się na obrazie stołu lasera. Można położyć na stole kilka
plików, przesuwać je myszą, skalować i obracać uchwytami albo wpisać ich
pozycję, rozmiar i kąt. Edytor ma cofanie i ponawianie, siatkę z
przyciąganiem, przyciąganie do innych obiektów, duplikowanie, wyrównywanie,
grupowanie, operacje na kształtach (suma, różnica, część wspólna) i listę
elementów, w której można wyłączyć element z zadania. Pasek narzędzi z
opisanymi grupami (Plik, Edycja, Układ, Widok), w stylu MeerK40t, daje szybki
dostęp do poleceń. Sterowanie maszyną (połączenie, bazowanie, objazd konturu,
start, stop) jest w panelu po lewej. Na początku zadania głowica najpierw
podjeżdża do projektu. **Ustaw projekt przy głowicy** zachowuje sposób pracy z
K40 Whisperera, w którym projekt zaczyna się tam, gdzie stoi głowica, a
przycisk **Projekt podąża za głowicą** (z łańcuchem, pod kłódką) trzyma go przy
głowicy, gdy ją przesuwasz.

Kerfly przesuwa głowicę strzałkami, do narożników projektu albo do podanej
pozycji. Wykonuje grawer rastrowy, grawer wektorowy, cięcie, G-code i objazd
konturu. Szacuje czas zadania, zapisuje zadania jako pliki EGV i wysyła
istniejące pliki EGV. Na płytach M3 ma też test wiązki i osobną moc dla każdej
operacji. Długie zadania działają w tle. Pauza na chwilę zatrzymuje laser, a
ten sam przycisk wznawia pracę. Stop natychmiast kończy zadanie. K40 nie
podaje, gdzie jest głowica, więc po Stop Kerfly prosi o bazowanie przed
następnym zadaniem. Przed wysłaniem czegokolwiek Kerfly sprawdza, czy głowica
przez całe zadanie zostaje na stole, i odmawia wysłania zadań, które
wjechałyby nią w ramę.

Oryginalne okno K40 Whisperera (`k40_whisperer.py`) nadal jest dołączone i
korzysta z tego samego rdzenia. Trybu wsadowego (batch) nie ma jeszcze w
nowym oknie.

Plany: pozostałe funkcje K40 Whisperera, więcej formatów plików, zawiasy
giętkie, wektoryzacja bitmap i kompensacja kerfu. Zobacz
[ROADMAP.md](ROADMAP.md) (po angielsku).

Dane dla lasera (EGV wysyłane przez USB) są po każdej zmianie porównywane bajt
w bajt z oryginalną wersją 0.71. Zobacz [Testy regresji](#testy-regresji).

Zmiany między wersjami są w [CHANGELOG.md](CHANGELOG.md) (po angielsku).

## Rysowanie i edycja: mysz i klawisze

| Czynność | Jak |
|---|---|
| Zaznaczenie kilku elementów | Przeciągnij wokół nich ramkę albo Ctrl+klik |
| Przesuwanie | Przeciągnij albo strzałki (1 mm albo jedno oczko siatki; Shift: 10×) |
| Przyciąganie | Do narożników, środków, połówek i linii innych elementów, do stołu i do siatki (**Widok → Przyciągaj do obiektów**, Ctrl+;) |
| Chwilowo bez przyciągania | **Przytrzymaj Alt** przy rysowaniu, przeciąganiu albo przesuwaniu węzła |
| Kwadrat / koło, linie co 45° | Przytrzymaj Shift przy rysowaniu |
| Łamana | Klikaj narożniki. Kliknij pierwszy punkt, żeby zamknąć; dwuklik albo Enter kończy otwartą linię; Backspace usuwa ostatni narożnik; Esc anuluje |
| Pióro (B) | Klik daje narożnik, wciśnięcie i przeciągnięcie daje gładką krzywą. Kliknij pierwszy punkt, żeby zamknąć; dwuklik albo Enter kończy; Backspace usuwa ostatni węzeł |
| Odręcznie (F) | Rysuj z wciśniętym przyciskiem; skończ blisko początku, żeby zamknąć kształt |
| Miarka (M) | Przeciągnij między dwoma punktami: odległość, szerokość, wysokość, kąt |
| Edycja węzłów (N) | Przeciągaj węzły i okrągłe uchwyty krzywych (Ctrl: jeden uchwyt osobno). Shift+klik zaznacza więcej. Dwuklik na boku dodaje węzeł, na węźle go usuwa. Klawisze: I wstaw, D usuń, L linia, C krzywa, O gładki, S symetryczny, Z zamknij / otwórz, B rozdziel |
| Edycja otwartego SVG / DXF | Rozgrupuj go: każda linia staje się osobnym kształtem, a obraz dzieli się na osobne części; klik przesuwa, dwuklik edytuje węzły |
| Edycja węzłów dowolnego elementu | Dwuklik na nim |
| Grupuj / Rozgrupuj | Ctrl+Shift+G / Ctrl+Alt+G. Klik w jeden element grupy zaznacza całą grupę |
| Lista elementów | Pokazuje, co jest zaznaczone na stole; klik w wiersz (Ctrl / Shift: kilka) zaznacza na stole |
| Powiększenie | Kółko myszy przybliża; nie oddala bardziej niż cały stół |
| Przesuwanie i powiększanie widoku | Środkowy albo prawy przycisk myszy przesuwa widok; kółko przybliża |

W KDE Plasma 5 Alt+przeciąganie domyślnie przesuwa okna. Zmienisz to w
Ustawieniach systemowych → Zarządzanie oknami → Zachowanie okien → Działania
okien. W Plasmie 6 okna przesuwa się klawiszem Meta.

## Instalacja

Zobacz [INSTALL_pl.md](INSTALL_pl.md) ([wersja angielska](INSTALL.md)).
Kerfly uruchamia się przez `start_kerfly.bat` w Windows albo
`./start_kerfly.sh` w Linuksie. Pierwsze uruchomienie przygotowuje Pythona i
biblioteki.

Instalację sprawdza `start_kerfly.bat --self-test` (Windows) albo
`./start_kerfly.sh --self-test` (Linux). Autotest pokazuje biblioteki,
sterownik USB, czy K40 jest podłączony (bez ruszania nim), Inkscape, folder
ustawień i czy okno otwiera projekt. Dołącz jego wynik do zgłoszenia błędu.

## Zgłaszanie problemów

W Kerfly wybierz **Pomoc → Zgłoś problem na GitHubie…** (albo przycisk **Zgłoś
błąd**). Kerfly zapisze raport diagnostyczny (ustawienia, autotest i dziennik
tego, co poszło do lasera) i otworzy
[formularz zgłoszenia](https://github.com/cyryllo/Kerfly/issues/new/choose) z
wpisaną wersją, systemem i płytą. Przeciągnij plik raportu do formularza. Są
formularze dla problemów z laserem (złe miejsce, moc albo prędkość), innych
błędów, pomysłów na funkcje i poprawek tłumaczeń. Formularze są po angielsku,
ale **zgłoszenie możesz napisać po polsku**.

## Uruchamianie ze źródeł (Debian / Ubuntu)

```bash
sudo apt install python3-venv python3-tk inkscape
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-optional.txt
.venv/bin/python kerfly.py               # nowe okno
.venv/bin/python k40_whisperer.py        # oryginalne okno K40 Whisperera
```

Inkscape jest opcjonalny. Jeśli jest zainstalowany, Kerfly używa go do
rastrów z SVG (jak K40 Whisperer). Jest też potrzebny do tekstu w SVG, który
ma być cięty albo grawerowany jako obrys. Bez niego Kerfly rysuje rastry SVG
własnym rendererem.

Dostęp do USB bez uprawnień roota wymaga reguły udev. Zobacz
[README_Linux.txt](README_Linux.txt).

## Uruchamianie ze źródeł (Windows)

Zainstaluj Pythona 3.13 (Inkscape jest opcjonalny), potem uruchom
`pip install -r requirements.txt` i `python kerfly.py`. Laser potrzebuje
sterownika libusb-win32, który zainstalujesz programem
[Zadig](https://zadig.akeo.ie/).

## Języki

Kerfly jest dostępny po angielsku, polsku, niemiecku, hiszpańsku i
francusku. Domyślnie używa języka systemu. Zmienisz go w **Ustawienia →
Zaawansowane → Język**.

Tłumaczenia niemieckie, hiszpańskie i francuskie nie zostały jeszcze
sprawdzone przez rodzimych użytkowników. Poprawki są mile widziane.

Żeby przetłumaczyć Kerfly na inny język albo poprawić tłumaczenie:

1. Zainstaluj narzędzia programistyczne: `pip install -r requirements-dev.txt`
2. Żeby dodać język, dopisz jego kod do `LANGUAGES` w `kerfly/i18n.py` i
   uruchom `python tools/i18n.py`. Powstanie plik
   `kerfly/locale/<kod>/LC_MESSAGES/kerfly.po`.
3. Przetłumacz plik `.po`, na przykład w [Poedit](https://poedit.net/).
4. Uruchom `python tools/i18n.py`, żeby go skompilować, a potem
   `python tests/test_i18n.py`, żeby go sprawdzić.

Programiści: każdy tekst widoczny dla użytkownika otocz `_()`, a teksty w
tabelach tłumaczonych później `N_()`. Potem uruchom `python tools/i18n.py`.

## Układ projektu

- `kerfly/core/`: rdzeń sterowania laserem, niezależny od interfejsu. Zawiera
  wczytywanie SVG, DXF i G-code, obsługę pliku ustawień, dane projektu,
  przygotowanie rastra, kolejność ścieżek i generowanie zadań EGV. Nic w nim
  nie importuje biblioteki okienkowej.
- `kerfly/gui/`: nowy interfejs w PySide6. Uruchamia go `kerfly.py`.
- `k40_whisperer.py`: oryginalny interfejs w Tkinterze. Korzysta teraz z
  `kerfly.core`.
- `egv.py`, `nano_library.py`: kodowanie EGV i komunikacja USB z płytą
  sterującą. Są niezmienione względem K40 Whisperera.
- `tests/`: testy regresji.

## Testy regresji

```bash
.venv/bin/python tests/test_core.py          # sam rdzeń, bez ekranu
.venv/bin/python tests/test_gui.py           # nowe okno, bez wyświetlania
.venv/bin/python tests/test_i18n.py          # tłumaczenia kompletne i aktualne
sudo apt install xvfb
xvfb-run -a .venv/bin/python tests/regression.py   # cała aplikacja
```

Jest 25 przypadków testowych. Obejmują cięcie, grawer wektorowy, raster,
objazd konturu i G-code, płyty M1/M2/M3/B1, obrót, lustro, bazowanie w prawym
górnym rogu i wiele przejść. Każdy przypadek porównuje dokładne bajty, które
dostałby laser, z wzorcem z niezmienionej wersji 0.71. Tryb mocy M3 jest
przechwytywany przez udawane urządzenie USB. Wzorce oparte na SVG zależą od
wersji Inkscape (obecnie 1.4). Bez Inkscape te przypadki są pomijane.

GitHub Actions uruchamia każdy push na czystych maszynach z Windows i Ubuntu.
Instaluje Kerfly przez `start_kerfly.bat` / `start_kerfly.sh`, uruchamia
autotest, a potem wszystkie powyższe zestawy testów. Na tych maszynach nie ma
Inkscape, więc przypadki oparte na SVG są tam pomijane. Wszystkie pozostałe
dane dla lasera są sprawdzane bajt w bajt także w Windows.

## Licencja

Kerfly jest wolnym oprogramowaniem na licencji **GNU General Public License w
wersji 3 lub późniejszej** (GPL-3.0-or-later). Zobacz [LICENSE](LICENSE).

- Copyright (C) 2017–2026 Scorch: oryginalny K40 Whisperer.
- Copyright (C) 2026 Kerfly contributors: zmiany wprowadzone w tym forku.

Niektóre pliki pochodzą z innych projektów (rozszerzenia Inkscape, biblioteka
kodu prędkości na licencji MIT, drobne fragmenty z publicznych stron) i mają
własne informacje o licencji.
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) wymienia każdy plik, jego
autora i licencję.

## Podziękowania i zastrzeżenie

Cała zasługa za rdzeń sterowania laserem należy do **Scorcha**, autora K40
Whisperera. Kerfly jest niezależnym forkiem, niezwiązanym ze Scorchem ani ze
scorchworks.com i przez nich niepopieranym. Błędy Kerfly zgłaszaj tutaj, nie
autorowi K40 Whisperera.

Ten program steruje laserem. Jest dostarczany BEZ JAKIEJKOLWIEK GWARANCJI
(zobacz punkty 15–16 licencji GPL). Nigdy nie zostawiaj pracującego lasera bez
nadzoru.
