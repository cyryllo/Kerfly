# Lista zmian Kerfly (po polsku)

Polska wersja opisów wydań, od 1.4.0. Pełna historia jest w
[CHANGELOG.md](CHANGELOG.md) (po angielsku).

## 2.0.0 (w przygotowaniu)

Oprócz K40 lasery z płytą GRBL: zapis G-code dla dowolnego programu
wysyłającego albo sterowanie laserem prosto z Kerfly przez port szeregowy, z
prędkościami w mm/min. Układanie części na stole, łączenie luźnych linii w
polilinie. Rozwijana na gałęzi `2.0`, z poprawkami wydań 1.x.

Nowy wygląd: przejrzystsza wstążka, pasek opcji w dwóch wierszach przez całe
okno, płaski panel po lewej, okna z nazwaną czynnością, symulacja w osobnym
oknie.

### Dodane

- **Połącz w polilinię** (Ctrl+J; menu Edycja, grupa Kształty na wstążce, menu
  pod prawym przyciskiem): zaznaczone linie, łamane i otwarte ścieżki, których
  końce się stykają (bliżej niż 0,05 mm), stają się jedną ścieżką, ciętą
  jednym ciągiem, zamkniętą, gdy łańcuch się domyka (jak Auto-Join w
  LightBurnie albo Polyline from Segments w QCAD). Zamknięte obrysy i linie,
  które z niczym się nie stykają, zostają bez zmian.
- **Ułóż na stole** (Ctrl+Shift+N; przycisk **Ułóż** w grupie Układ na wstążce,
  menu Edycja, menu pod prawym przyciskiem): zaznaczone części (grupa jako
  jedna część) rozkładane na stole lasera tak ciasno, jak pozwalają ich
  prostokąty, z odstępem, obracane o 90°, gdy tak lepiej się mieszczą (można
  wyłączyć); co się nie zmieści, trafia na kolejne arkusze, każdy jako grupa
  na liście elementów, arkusze od 2. odhaczone. Generatory pudełek używają
  tego samego układania. **Metoda: Obrysy** (beta) układa prawdziwe obrysy
  części zamiast ich prostokątów, biblioteką sparrow: części trafiają we wnęki
  innych i w wycięte w nich otwory (otwór robią tylko linie cięcia), szukając
  przez zadany czas (dla każdego arkusza, w okienku z Anuluj).
- **G-code dla laserów GRBL**: Plik → Zapisz G-code… (Ctrl+Shift+K,
  przycisk **G-code** w grupie Plik na wstążce) zapisuje zaznaczone warstwy
  (raster linia po linii z najazdem, grawer, cięcie) z ich prędkością, mocą i
  przejściami, w trybie lasera M4, dla LaserGRBL, UGS albo innego programu
  wysyłającego. Początek w lewym dolnym rogu stołu albo w lewym górnym rogu
  projektu, pełna moc S (`$30`) i najazd są zapamiętywane w profilu lasera.
  Przetestowane na laserze GRBL.
- **Lasery GRBL podłączone do Kerfly**: Ustawienia → Lasery… → Maszyna:
  płyta GRBL, port szeregowy (port, prędkość, róg bazowania, prędkość
  przesuwu i pełna moc S, zapamiętywane w profilu lasera). Działają na nim
  Połącz, Bazuj (`$H`), Odblokuj (`$X`), strzałki i przyciski narożników
  (przesuw), Obrys, Start (G-code wysyłany od lewego górnego rogu projektu
  jako X0 Y0, bez przepełniania bufora płyty), Pauza / wznowienie (`!` / `~`)
  i Stop (reset). Potrzebuje biblioteki pyserial (jest w paczkach). Przy
  maszynie GRBL prędkości są pokazywane i wpisywane w mm/min (warstwy, test
  materiału, Ustawienia, biblioteka materiałów); K40 zostaje w mm/s.
- **Baza materiałów dla każdego lasera**: Ustawienia → Lasery… → Baza
  materiałów: własna albo wspólna z innym laserem tego samego rodzaju (laser
  zrobiony przez Powiel dzieli bazę z oryginałem). Dotychczasowa wspólna baza
  zostaje przy pierwszym laserze, pozostałe z niej korzystają, więc nic się nie
  zmienia, dopóki sam tego nie wybierzesz.
- **Prędkość bazowania GRBL** (Ustawienia → Lasery… → Ruch głowicy, obok
  prędkości przesuwu strzałkami): zapisywana w płycie (`$25`) przy łączeniu,
  gdy się różni.
- **Uchwyty boków**: środki boków zaznaczonego elementu zmieniają samą
  szerokość albo samą wysokość, przeciwległy bok zostaje na miejscu (także dla
  obróconego elementu; jeden krok cofania).
- **O programie** w osobnym oknie: wersja, licencja, pochodzenie, strona
  projektu, **Zgłoś problem** i **Sprawdź aktualizacje**.

### Zmienione

- **Nowy wygląd** (motyw jasny i ciemny): jeden zestaw rozmiarów, odstępów i
  kolorów dla całego okna.
- **Wstążka**: grupy Plik, Edycja, Układ, Kształty, Widok i Narzędzia;
  generatory na jednej liście **Generatory** (pudełka, elementy, testy i
  kalibracja), także w menu; Zgłoś problem i raport diagnostyczny tylko w
  menu Pomoc, Lasery na zakładce Laser; Obrysuj obraz wśród narzędzi
  rysowania po prawej, Edytuj węzły (N) w grupie Edycja (klik w puste miejsce
  stołu kończy edycję i wraca do zaznaczania).
- **Pasek opcji** przez całe okno pod wstążką, w dwóch wierszach: zawsze
  zaznaczenie (X, Y, Szer., Wys., obrót, warstwa), potem to, co edytujesz;
  każde pole z ikoną, krótkim podpisem i podpowiedzią; narzędzie węzłów
  pokazuje same swoje przyciski, jako ikony.
- **Panel po lewej** płaski: Projekt (Elementy z liczbą i rozmiarem, Warstwy
  z jednostkami w nagłówku tabeli i **Dodaj warstwę**) i Laser (Urządzenie:
  laser w użyciu i kropka stanu; Ruch głowicy: Połącz, Bazuj, Odblokuj silniki
  i Za głowicą jako kwadratowe przyciski obok krzyżaka, tej samej wysokości);
  **Obrys**, **Start**, **Pauza** i **Stop** równej szerokości na dole obu
  zakładek.
- **Ustawienia każdego lasera w Ustawienia → Lasery…** (zębatka przy liście
  laserów): lista laserów po lewej, ustawienia zaznaczonego po prawej (płyta,
  stół, bazowanie, programy przed zadaniem i po nim, skala, moc, objazd
  konturu, oś obrotowa, USB, GRBL), także lasera, który nie jest w użyciu;
  Zapisz zapisuje zmiany wszystkich zmienionych laserów. Ustawienia →
  Ustawienia… mają już tylko ustawienia programu (raster, kolejność cięcia,
  widok z jednostkami, język, aktualizacje, Inkscape).
- **Cztery rogi bazowania dla każdego lasera** (Ustawienia → Lasery… → Stół
  roboczy → Róg bazowania: obrazek stołu z przyciskiem wyboru w każdym rogu,
  tak samo dla K40 i lasera GRBL; zastępuje pole „pozycja bazowa w prawym
  górnym rogu” i listę rogów GRBL). Bazowanie stawia głowicę w tym rogu, a
  **Do głowicy** i **Projekt podąża za głowicą** przysuwają do głowicy ten sam
  róg projektu (wcześniej zawsze lewy górny, więc przy bazie na dole projekt
  lądował pod stołem). Górne rogi K40 wysyłają te same dane co dotąd.
- **Nadmuch powietrza dla lasera GRBL** (Ustawienia → Lasery… → Sterownik):
  `M8` na początku zadania, `M9` na końcu (także w Zapisz G-code); domyślnie
  wyłączony, G-code jak dotąd.
- **Ustawienia lasera pokazują tylko to, co ma jego maszyna**: laser GRBL nie
  ma pól płyty K40, USB, ustawienia mocy ani odblokowania osi (ich sekcje są
  ukryte), K40 nie ma pól GRBL (wcześniej były wyszarzone); okno dla lasera
  GRBL ukrywa strzał testowy i pliki EGV i pokazuje „Połączono (GRBL)”.
- **Laser GRBL ma moc dla każdej warstwy** (i moc objazdu konturu), niezależnie
  od ustawienia płyty K40.
- **Nazwę lasera** zmienia się w polu nad jego ustawieniami (wpisz, Enter), a
  nie na liście.
- **Pasek stanu**: miejsce kursora myszy, rozmiar stołu, powiększenie i stan
  lasera.
- **Okna**: najpierw Anuluj, potem przycisk nazwany czynnością (**Zapisz**,
  **Wstaw obraz**, **Usuń laser**, **Zatrzymaj i zakończ**…, nigdy OK),
  sekcje, znaczki **beta**; Ustawienia z kategoriami na liście i stronami w
  sekcjach; baza materiałów jako tabela; nowy układ okien Lasery, Obrysuj
  obraz, Rozmiar obrazu, Który laser? i Skróty klawiszowe.
- **Symulacja zadania** w osobnym oknie z własnym podglądem (całe zadanie
  szare, wypalone na czerwono): Odtwórz, czas, tempo, Następna warstwa,
  wypalana warstwa; startuje z tempem 5× (dłuższe zadanie szybciej). Otwarta podczas zmian projektu przelicza zadanie i zostaje
  w tym samym miejscu; Nowy i Otwórz ją zamykają.

### Poprawione

- **Zamykanie się programu**: na Linuksie spakowany program potrafił się
  wysypać przy zamykaniu (już po zniknięciu okna), a czasem w trakcie pracy
  (wklejanie, układanie). Pola panelu i paska są teraz usuwane bezpiecznie,
  program kończy pracę bez sprzątania Qt przy wyjściu, a awaria zapisuje,
  gdzie się zdarzyła: następny start wpisuje to do logu (Pomoc → Zgłoś
  problem go wysyła).
- **Prędkość bazowania GRBL** usunięta z ustawień lasera: płyta zostaje przy
  swojej (`$25`); Kerfly nie zapisuje jej już przy łączeniu (Beta 2 i 3
  zapisywały ją, gdy była ustawiona: sprawdź `$25` w LaserGRBL, jeśli płyta
  bazuje teraz z inną prędkością niż wcześniej).
- **Zawias giętki** (narzędzie, karta testowa, okrągłe pudełko): sklejka się
  nie wyginała, bo wzdłuż obrysu biegł pełny brzeg. Teraz krótkie nacięcia
  dochodzą do obrysu na końcach co drugiego rzędu, długie mają mostek na obu
  końcach, mostki sąsiednich rzędów nigdy nie są w jednej linii, każdy rząd
  jest rozkładany na swoją długość (bez ścinków), a margines zostaje tylko na
  końcach zawiasu (domyślnie 0).
- **Kolejność cięcia**: kształt leżący w środku cięcia innego elementu jest
  cięty pierwszy (kółko narysowane po kwadracie, w którym leży, zgrupowane
  czy nie, było cięte po kwadracie, który mógł wcześniej wypaść); poza tym
  zostaje kolejność z listy elementów.
- **Ułóż na stole po obrysach** rozrzucał części wzdłuż lewej krawędzi stołu
  (2.0.0b2): części arkusza są teraz układane drugi raz w poprzek, razem w
  jego lewym górnym rogu.
- **Uruchamianie ze źródeł** (`start_kerfly.sh`, `start_kerfly.bat`):
  dodatkowe biblioteki dodane w aktualizacji też są instalowane przy
  następnym starcie (kto uruchamiał 2.0.0b1 ze źródeł, nie miał spyrrow i
  Ułóż po obrysach był wyszarzony).

## 1.8.0 (2026-11-16)

Podgląd 3D pudełek z generatora, grupy w grupach (arkusze i części pudełka na
liście elementów), mocniejsze wysuwane wieczko; po przycisku narożnika
strzałki zachowują miejsce głowicy na projekcie.

### Dodane

- **Podgląd pudełek w 3D**: okno generatora pudełka na wczepy i okrągłego
  pudełka ma obok płaskiego widoku **Części** zakładkę **3D**. Pokazuje
  pudełko złożone z tych samych części, które zostaną wycięte; przeciąganie
  obraca, kółko przybliża. **Rozsunięte** odsuwa części od siebie, żeby
  pokazać połączenia, **Ukryte krawędzie** pokazuje krawędzie schowane za
  innymi częściami linią przerywaną, a suwak wysuwa wysuwane wieczko z rowka.
  Każda ściana jest rysowana w kolejności, w jakiej ściany się zasłaniają
  (także tam, gdzie wczepy i języczki wchodzą w szczeliny), więc przy
  obracaniu nic nie prześwituje ani nie znika; zgięta ścianka okrągłego
  pudełka ma swoje szczeliny.
- **Grupy w grupach**, pokazane na liście elementów jako drzewo: grupa to
  wiersz, który się rozwija i zwija, ptaszek przy niej włącza ją całą do
  zadania albo wyłącza, a klik w jej wiersz zaznacza tylko tę grupę (klik w
  wiersz elementu tylko ten element). Pudełko z generatora to jedna grupa z
  osobną grupą dla każdego arkusza (**Arkusz 1**, **Arkusz 2**, …, gdy jest
  ich kilka) i dla każdej części złożonej z kilku kształtów (obrys i jego
  szczeliny), części ułożone arkuszami po kolei. **Rozgrupuj** zdejmuje
  jeden poziom; kopie i zapisane projekty zachowują grupy i ich nazwy.

### Zmienione

- **Arkusze pudełka z generatora są na warstwie cięcia** (jeden kolor), a nie
  na osobnych, odhaczonych warstwach: każdy arkusz to grupa na liście
  elementów, arkusze od 2. są na początku odhaczone; odhacz wycięty arkusz i
  zaznacz kolejny. (Gdy arkusz był zaznaczony na liście, a jego warstwa
  odhaczona, Symulacja i Start nie miały nic do zrobienia.)
- **Wysuwane wieczko (beta): nad górną listwą zostaje pas bocznej ścianki**
  (co najmniej 3 mm albo grubość materiału), więc górna krawędź jest
  mocniejsza; języczki listwy wchodzą w zamknięte szczeliny zamiast w
  wycięcia krawędzi, a rowek, wieczko i niższy przód schodzą o tyle samo.
- **Podsumowanie w oknie generatora liczy warstwy, których projekt używa**:
  dla pudełka na domyślnej warstwie cięcia pokazywało „warstw: 0”.
- **Kerfly.exe i instalator dla Windows mają nazwę produktu i wersję**
  (widoczne we Właściwościach pliku), przygotowane do podpisywania kodu.

### Poprawione

- **Po przycisku narożnika strzałki wyrzucały projekt poza stół** przy
  włączonym „Projekt podąża za głowicą”: głowica wracała do punktu
  odniesienia projektu (przy bazowaniu w prawym górnym rogu do jego prawego
  górnego rogu), a projekt przesuwał się o całą tę odległość. Teraz projekt
  przesuwa się razem z głowicą, a głowica zostaje w tym samym miejscu
  projektu (np. w jego lewym górnym rogu, żeby sprawdzić, czy nie wychodzi
  poza materiał); projekt i głowica zostają na stole, jak w K40 Whisperer.

## 1.7.1 (2026-11-15)

### Poprawione

- **Lista czcionek narzędzia Tekst pokazywała inną czcionkę niż w tekście** na
  komputerze z małą liczbą czcionek („Sans Serif” zamiast „DejaVu Sans”), a
  czcionka, której nie ma na komputerze, nie była zachowywana. Lista pokazuje
  teraz czcionkę tekstu, a tekst zachowuje czcionkę, której na tym komputerze
  brakuje.

## 1.7.0 (2026-11-15)

Czcionki jednokreskowe, dziesięć nowych wzorów wypełnienia, metody ditheringu,
wektoryzacja i wycinanie obrazków, pudełka z przegródkami, wysuwanym wieczkiem
i zaokrąglonymi rogami (beta), port USB każdego lasera (beta).

### Dodane

- **Czcionki jednokreskowe** do szybkiego grawerowania, wbudowane w Kerfly
  (18 czcionek Hershey i EMS, bez Inkscape): na górze listy czcionek narzędzia
  Tekst. Każda litera to kilka linii, po których laser przejeżdża raz, zamiast
  konturu do wypełnienia; polskie litery (ą, ę, ł, ń, ś, ź, ż) są składane z
  litery i znaku. Działają też w tekście na ścieżce. Tekst rastrowy
  przełączony na taką czcionkę jest grawerowany wzdłuż linii.
- **Dziesięć nowych wzorów wypełnienia** (razem 19): trójkąty, jodełka, łuski,
  fale prostokątne, spirala, promienie, kropki, krzyżyki, kafelki Truchet i
  krzywa Hilberta, w sekcji Wypełnienie paska opcji.
- **Metody ditheringu** dla zdjęć i obrazów w skali szarości (Ustawienia →
  Raster → Metoda ditheringu): Floyd-Steinberg (jak dotąd, domyślna), Atkinson
  (większy kontrast, czyste jasne miejsca: dobra na drewno), Jarvis, Stucki,
  Burkes i Sierra (gładsze przejścia), uporządkowany Bayer (równa faktura) i
  próg.
- **Wektoryzuj obrazek** (przycisk zaznaczonego obrazka, Edycja → Wektoryzuj
  obrazek…, pasek Kształty): ciemne miejsca obrazka stają się ścieżkami na nim,
  do cięcia, obrysu, wypełnienia albo edycji węzłów. Próg, pomijanie drobinek,
  dokładność i gładkie krzywe (ostre narożniki zostają ostre), z obrysami
  widocznymi na tle obrazka podczas ustawiania.
- **Przegródki w pudełku** (beta, jeszcze nie sprawdzone na laserze): pudełko
  z wczepami dostaje wewnętrzne ścianki w poprzek i wzdłuż, rozłożone równo,
  z wypustami w szczelinach ścianek i dna; krzyżujące się przegródki łączą
  nacięcia do połowy wysokości.
- **Wysuwane wieczko** (beta, jeszcze nie sprawdzone na laserze) w pudełku z
  wczepami: wieczko wsuwa się od przodu w rowek między dwiema poziomymi
  listwami na każdej bocznej ściance, trzymanymi języczkami w szczelinach
  ścianki; przód jest niższy.
- **Pudełka lepiej wykorzystują stół**: części są obracane, gdy to pomaga, i
  dokładane w wolne miejsca wcześniejszych arkuszy (pudełko 250 × 180 × 60 mm:
  3 arkusze zamiast 4).
- **Okrągłe pudełko na zawiasie** (beta, jeszcze nie sprawdzone na laserze):
  nowy generator; zaokrąglone dno i wieko z wypustami, ścianka z dwóch pasków,
  które gną się na rogach; bez wieka kształt u góry trzyma obrzeże.
- **Port USB dla każdego lasera** (beta, jeszcze nie sprawdzone z dwoma
  laserami): przy dwóch K40 podłączonych do jednego komputera profil każdego
  lasera pamięta port USB swojej płyty (Ustawienia → Maszyna → Port USB, **Który
  to?** rusza lekko jego głowicą); bez zapamiętanego portu Kerfly pyta, z którym
  laserem się połączyć, i zapamiętuje odpowiedź.
- Narzędzie **Wytnij fragment obrazka** (pasek po prawej, Shift+C): przeciągnij
  prostokąt albo elipsę po obrazku; fragment w środku zostaje na swoim
  miejscu, reszta znika.

### Poprawione

- Przycisk **Wstaw** w generatorach był zawsze po angielsku; teraz jest
  przetłumaczony (test pilnuje, żeby takie napisy nie umykały).

## 1.6.0 (2026-11-14)

Profile laserów, ciemny motyw, wszystkie skróty klawiszowe w jednym oknie,
projekty .kerfly otwierane dwuklikiem, węższy pasek narzędzi.

### Dodane

- **Ciemny motyw**: Ustawienia → Widok → Motyw: jasny, ciemny albo jak w
  systemie (po ponownym uruchomieniu). Stół lasera zostaje jasny, bo
  przedstawia materiał.
- **Pomoc → Skróty klawiszowe** (Ctrl+F1): wszystkie klawisze z menu i
  narzędzi rysowania oraz działania myszą w jednym oknie, z wyszukiwaniem.
- **Projekty .kerfly otwierają się w Kerfly dwuklikiem**: opcja instalatora
  Windows (zaznaczona), **Ustawienia → Dodaj Kerfly do menu aplikacji…** dla
  AppImage na Linuksie (dodaje też Kerfly do menu pulpitu; nowsze AppImage
  samo poprawia wpis) oraz na macOS.
- Minimalny rozmiar okna (1024 × 680 albo cały ekran, gdy jest mniejszy).
- **Profile laserów**, dla więcej niż jednego lasera (np. laptop przenoszony od
  jednej maszyny do drugiej): lista na górze zakładki Laser wybiera laser w
  użyciu, a jego ustawienia (płyta, stół, pozycja bazowa, skala, moc, oś
  obrotowa, objazd konturu, programy przed zadaniem i po nim) trafiają do
  okna. Ustawienia → Lasery… (na pasku **Lasery**) dodaje, duplikuje, zmienia
  nazwę, usuwa, eksportuje i importuje lasery. Ustawienie maszyny zmienione w
  Ustawieniach zapisuje się w profilu w użyciu; przy pierwszym uruchomieniu
  obecne ustawienia stają się „Moim laserem”. Jeden laser naraz.

### Zmienione

- Pasek narzędzi jest węższy (o około 290 pikseli w Full HD po polsku): mieści
  się teraz na ekranie 1920 pikseli; w wąskim oknie grupy, które się nie
  mieszczą, chowają się pod przyciskiem », zamiast obcinać napisy.
- Generatory są za Ustawieniami, w menu i na pasku narzędzi.
- Bez przycisku **Aktualizacje** na pasku: Pomoc → Sprawdź aktualizacje.
- Ustawienia mocy (moc dla każdej operacji, moc maksymalna, moc objazdu) są
  wyszarzone, gdy nie jest wybrana płyta M3: inne płyty nie sterują mocą, ustawia
  ją pokrętło lasera.

## 1.5.0 (2026-11-14)

Programy przed zadaniem i po nim (włączenie i wyłączenie wyciągu), raport z
czasem zadania, moc objazdu konturu.

### Dodane

- **Moc objazdu konturu z włączonym laserem**: Ustawienia → Wektory, zaraz pod
  *Objazd konturu z włączonym laserem* (wyszarzona, gdy ta opcja jest
  wyłączona), w procentach mocy maksymalnej. Płyta M3 dostaje ją podczas
  objazdu; na innych płytach moc ustawia jak dotąd pokrętło lasera.
- **Raport po zadaniu** (Ustawienia → Maszyna, domyślnie włączony): małe okno
  z czasem zadania, które czeka, aż wrócisz do lasera (nie blokuje Kerfly).
  Nie pojawia się po objeździe konturu.
- **Uruchom program przed zadaniem** (Ustawienia → Maszyna): np. żeby włączyć
  wyciąg albo pompę powietrza. Zadanie czeka, aż program się skończy (najwyżej
  minutę); gdy nie zadziała, Kerfly pyta, czy mimo to rozpocząć zadanie. Nie
  przed objazdem konturu.
- **Uruchom program po zadaniu** (Ustawienia → Maszyna): program albo skrypt
  (.bat, .sh) uruchamiany po każdym skończonym zadaniu, np. żeby wyłączyć
  wyciąg albo wysłać wiadomość; jego wynik i błędy są pokazane w raporcie
  (błędy także przy wyłączonym raporcie).

### Zmienione

- Ustawienia → Oś obrotowa: współczynnik skali i prędkość szybkich ruchów są
  wyszarzone, gdy oś obrotowa jest wyłączona (tak jak moc objazdu bez
  włączonego lasera).

## 1.4.1 (2026-11-13)

Poprawki: pieczątka na Windows, materiały z więcej niż trzema warstwami,
wyśrodkowane przyciski Tylko grawer/obrys/cięcie.

### Poprawione

- **Pieczątka na Windows: paski w 1.4.0 nadal były.** Tekst jest teraz
  rysowany jako wypełnione kontury liter, a nie przez systemowy mechanizm
  rysowania tekstu, więc wychodzi tak samo na Windows, Linuksie i macOS (razem z
  pogrubieniem, kursywą, podkreśleniem i rozmiarami z edytora pieczątki). Gdy
  lista czcionek jest pusta, Windows używa Ariala.
- **Zapis materiału z obecnych warstw zapisywał tylko trzy podstawowe
  warstwy.** Dodatkowe warstwy (drugie cięcie, kolejny grawer…) zapisują się z
  nazwą, kolorem, prędkością, przejściami, mocą i szerokością cięcia, są
  widoczne w oknie materiałów w części *Inne warstwy* (każdą można zmienić albo
  usunąć) i tworzą się z powrotem po zastosowaniu materiału.
- Kolorowy kwadrat i napis na przyciskach Tylko grawer, Tylko obrys i Tylko
  cięcie są wyśrodkowane (przylegały do lewej krawędzi).

## 1.4.0 (2026-11-13)

Kopiuj i wklej, menu pod prawym przyciskiem, edytor tekstu pieczątki, pudełka
dopasowane do stołu, pochodzenie każdego projektu i sprawdzanie nowych wersji.

### Poprawione

- **Pieczątka: paski w literach i przerywana ramka na Windows** (w podglądzie,
  w symulacji i przy grawerowaniu). Pieczątka jest teraz rysowana w zwykłym kolorowym
  obrazie i dopiero potem zamieniana na czerń i biel, a gdy brakuje czcionki
  DejaVu Sans (na Windows), używany jest Arial zamiast sztucznie pogrubionej
  zastępczej.
- **Symulacja otwierała się podwójnie** po drugim kliknięciu; teraz drugie
  kliknięcie przywołuje otwarte okno.
- **Linux AppImage: pliki SVG nie otwierały się, gdy zainstalowany jest
  Inkscape** (program się zawieszał). Programy uruchamiane przez Kerfly
  (Inkscape, przeglądarka) dostawały biblioteki z AppImage i Inkscape padał na
  starszej bibliotece C++; teraz dostają systemowe.

### Nowe

- **Nowe wersje:** raz dziennie przy starcie Kerfly pyta GitHuba, czy wyszła
  nowa wersja (nic o Tobie ani o Twojej pracy nie jest wysyłane). Pasek nad
  stołem pokazuje ją wtedy z przyciskami **Zobacz wydanie**, **Później** i
  **Pomiń tę wersję**. **Pomoc → Sprawdź aktualizacje** (na pasku
  **Aktualizacje**) sprawdza od razu. Domyślnie włączone; wyłączysz w
  Ustawienia → Zaawansowane. Kerfly niczego sam nie pobiera ani nie instaluje.
- **Kopiuj, wytnij i wklej** jak w Inkscape: Ctrl+C, Ctrl+X, Ctrl+V (wkleja pod
  kursorem, gdy jest nad stołem, inaczej 5 mm dalej), Ctrl+Alt+V wkleja w
  miejscu; także do innego projektu w tym samym oknie (grupy zostają grupami,
  warstwy idą po nazwie). **Zaznacz wszystko** (Ctrl+A) i **Odznacz** (Esc na
  stole, Ctrl+Shift+A). W menu Edycja i w nowej grupie **Schowek** na pasku,
  razem z Duplikuj i Usuń.
- **Tylko grawer, Tylko obrys, Tylko cięcie**: jeden rodzaj pracy naraz (np.
  grawer, sprawdzenie, potem cięcie); każdy wykonuje wszystkie zaznaczone
  warstwy swojego rodzaju z ich ustawieniami. Małe przyciski nad Start, zawsze
  widoczne także na małym ekranie, włączane w Ustawienia → Widok (domyślnie
  wyłączone); są też w menu Laser. Podpowiedź pokazuje czas ich części.
- **Skąd pochodzi każdy projekt:** lista elementów pokazuje otwarty plik razem
  z folderem (Klient A › projekt.svg), a dolny pasek foldery i plik projektu
  pod kursorem (albo zaznaczonego), pełną ścieżkę w podpowiedzi; projekty o
  tej samej nazwie z różnych folderów (folder na każdego klienta) łatwo
  odróżnić. Zapisane projekty, kopie i części rozbitego pliku pamiętają, skąd
  pochodzą.
- **Edytor tekstu pieczątki**: tekst pieczątki prostokątnej piszesz w małym
  edytorze, który od razu pokazuje go tak, jak będzie wyglądał: **B**
  pogrubienie, **I** kursywa, **U** podkreślenie, **A+ / A−** większe i
  mniejsze litery, wyrównanie wierszy, dla każdego fragmentu tekstu (np.
  nazwa duża i pogrubiona, adres mniejszy).
- **Pudełko na wczepy dopasowane do stołu**: części są układane w obszarze
  roboczym; te, które się nie mieszczą, trafiają na kolejny arkusz w tym samym
  miejscu, na własnej odhaczonej warstwie cięcia (Arkusz 2, …). Opcja **Każda
  część na osobnej warstwie**.
- **Puzzle z okrągłymi wypustkami**: wąska szyjka i okrągła główka, każda
  wypustka trochę inna.
- **Bazowanie głowicy po zadaniu** (Ustawienia → Maszyna): po skończonym
  zadaniu głowica wraca do 0, 0, gotowa na kolejną sztukę, bez naciskania
  Bazowanie (nie po Stopie i nie po objeździe konturu). Projekt zostaje na
  miejscu; następny Start podjeżdża do niego głowicą.
- **Menu pod prawym przyciskiem** na stole (kliknięcie bez przeciągania;
  przeciąganie prawym przyciskiem dalej przesuwa widok). Na elemencie: jego
  polecenia, z **Warstwa ▸**, która jednym kliknięciem przenosi wszystkie
  zaznaczone elementy na inną warstwę (np. każdy projekt na osobną warstwę
  grawera, zgłoszenie #2), łączenie kształtów, kolejność, wyrównanie, obrót,
  odbicie, wypełnienie, edycja węzłów, **Pomiń w zadaniu**. Na pustym stole:
  **Przesuń głowicę tutaj** (projekt zostaje na miejscu), wklej, zaznacz
  wszystko, dopasuj widok, siatka.
