---
layout: default
lang: pl
title: Kerfly po polsku
other_lang: index.html
wide: true
description: Kerfly to darmowy program do sterowania laserami CO2 K40 z płytami Lihuiyu M2 Nano. Rysuj, układaj i tnij w Windows, Linuksie i macOS.
---
{% assign img = '/img/pl/' | relative_url %}

<div class="hero">
  <img src="{{ '/assets/logo.svg' | relative_url }}" alt="Logo Kerfly">
  <div>
    <h1>Kerfly</h1>
    <p>Darmowy program do sterowania laserami K40. Rysujesz, układasz i tniesz w jednym oknie.</p>
    <p class="badges"><span>Windows</span><span>Linux</span><span>macOS</span><span>Darmowy i otwarty</span><span>Po polsku</span></p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="#pobierz">Pobierz</a>
  <a class="button" href="{{ '/pl/guide.html' | relative_url }}">Instrukcja obsługi</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL_pl.md">Instalacja</a>
</div>

<div class="shot"><a href="{{ '/screenshot_pl.png' | relative_url }}"><img src="{{ '/screenshot_pl.png' | relative_url }}" alt="Główne okno Kerfly z rysunkiem na stole lasera"></a></div>

<p class="lead">Kerfly steruje laserami CO2 klasy K40 z <strong>płytami Lihuiyu</strong> (rodzina M2 Nano: M1, M2, M3, B1, …), czyli popularnymi niebiesko-białymi laserami biurkowymi sprzedawanymi pod wieloma nazwami. Wszystko, od pierwszego szkicu do wyciętej części, robisz w jednym nowoczesnym oknie: rysujesz, otwierasz pliki, układasz je na stole, ustawiasz warstwy, sprawdzasz zadanie i wysyłasz je do lasera.</p>

<div class="stats">
  <div><strong>10</strong><span>generatorów: pudełka, testy, pieczątki, QR, …</span></div>
  <div><strong>8</strong><span>wzorów wypełnień do graweru</span></div>
  <div><strong>3</strong><span>rodzaje zawiasów giętkich</span></div>
  <div><strong>3</strong><span>rodzaje warstw: raster, obrys, cięcie</span></div>
  <div><strong>1:1</strong><span>dane dla lasera sprawdzane bajt po bajcie</span></div>
</div>

## Co potrafi Kerfly

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-nodes.png"><img loading="lazy" src="{{ img }}site-nodes.png" alt="Edycja węzłów serca, z uchwytami krzywych"></a></div>
  <div class="text-col">
    <h3>Rysowanie i edycja jak w programie wektorowym</h3>
    <ul>
      <li>Prostokąt (także zaokrąglony), elipsa, wielokąt, linia, łamana, pióro do krzywych, rysowanie odręczne i tekst dowolną zainstalowaną czcionką.</li>
      <li>Edycja węzłów każdego kształtu i otwartych plików SVG i DXF: przeciągasz węzły i uchwyty krzywych, dodajesz, usuwasz, wygładzasz, rozcinasz.</li>
      <li>Przyciąganie do narożników, środków i krawędzi innych kształtów oraz do siatki; z Alt kładziesz swobodnie.</li>
      <li>Suma, różnica, część wspólna i wykluczenie kształtów.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col small"><a href="{{ img }}design.png"><img loading="lazy" src="{{ img }}design.png" alt="Lista elementów z przyciskami kolejności"></a></div>
  <div class="text-col">
    <h3>Układanie całego stołu</h3>
    <ul>
      <li>Kładziesz kilka plików i rysunków na obrazie stołu lasera; przesuwasz, skalujesz i obracasz je uchwytami albo wpisujesz dokładne liczby.</li>
      <li>Wyrównywanie, rozkładanie, odbicia, grupy, duplikaty; cofanie i ponawianie wszystkiego.</li>
      <li>Lista elementów to kolejność zadania: strzałkami obok niej ustawiasz, co idzie pierwsze. Otwory zawsze są cięte przed swoim obrysem.</li>
      <li>Projekt trzyma układ, warstwy i kopie Twoich plików w jednym pliku <code>.kerfly</code>.</li>
    </ul>
  </div>
</div>

<div class="showcase">
  <div class="shot-col small"><a href="{{ img }}layers.png"><img loading="lazy" src="{{ img }}layers.png" alt="Panel warstw z prędkością, przejściami i czasem każdej warstwy"></a></div>
  <div class="text-col">
    <h3>Warstwy jak w LightBurnie</h3>
    <ul>
      <li>Grawer rastrowy, obrys i cięcie, każda warstwa z własną prędkością, liczbą przejść, kolorem i, na płytach M3, mocą.</li>
      <li>Kilka warstw tego samego rodzaju (np. cięcie wolne i szybkie) i wybór warstwy dla każdego kształtu.</li>
      <li>Baza materiałów („Sklejka 3 mm”) ustawia wszystkie warstwy jednym wyborem; eksport i import.</li>
      <li>Czas każdej warstwy i całego zadania, zanim zaczniesz.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}site-fill.png"><img loading="lazy" src="{{ img }}site-fill.png" alt="Kształty wypełnione plastrem miodu, falami, cegłami, okręgami i rombami"></a></div>
  <div class="text-col">
    <h3>Wypełnienia wzorami</h3>
    <p>Wypełnij dowolny zamknięty kształt grawerowanymi liniami we wzór, a jego obrys nadal zostanie wycięty: linie, krzyżowe, fale, zygzak, okręgi, plaster miodu, romby i cegły. Ustawiasz wielkość, kąt i wolny margines; bierzesz wiaderko i klikasz kształty.</p>
    <p>Podkładka z wyciętym brzegiem i wygrawerowanym plastrem miodu w środku to dwa kliknięcia.</p>
  </div>
</div>

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-hinge.png"><img loading="lazy" src="{{ img }}site-hinge.png" alt="Zawiasy giętkie z nacięciami prostymi, falistymi i zygzakowatymi"></a></div>
  <div class="text-col">
    <h3>Zawiasy giętkie</h3>
    <p>Rzędy nacięć, dzięki którym sklejka się wygina: proste, faliste albo zygzakowate. Ustawiasz długość nacięć, mostki między nimi, odstęp rzędów i kierunek, a zawias możesz zawęzić do pasa tylko tam, gdzie część ma się zginać.</p>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}site-textpath.png"><img loading="lazy" src="{{ img }}site-textpath.png" alt="Tekst wokół okręgu i wzdłuż krzywej"></a></div>
  <div class="text-col">
    <h3>Tekst na ścieżce</h3>
    <p>Ułóż tekst wzdłuż linii, krzywej albo wokół okręgu, przesuwaj go myszą, zmieniaj odstęp liter, odległość od linii i stronę. Idealne na podkładki, tabliczki i pieczęcie.</p>
  </div>
</div>

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-generators.png"><img loading="lazy" src="{{ img }}site-generators.png" alt="Test materiału, pudełko na wczepy, koło zębate i pieczątka z generatorów"></a></div>
  <div class="text-col">
    <h3>Generatory: gotowe projekty z kilku liczb</h3>
    <ul>
      <li><strong>Test materiału</strong>: siatka pól, każde z własną prędkością i mocą albo liczbą przejść, na osobnej warstwie, z wygrawerowanymi wartościami.</li>
      <li><strong>Pudełko na wczepy</strong> z wiekiem albo bez, wymiary wewnętrzne lub zewnętrzne, kompensacja kerfu.</li>
      <li><strong>Test kerfu</strong>: zmierz, jak szeroko tnie Twój laser, i znajdź najciaśniejsze pasowanie.</li>
      <li><strong>Koło zębate</strong> z zębami ewolwentowymi, <strong>puzzle</strong>, <strong>linijka</strong>, <strong>kod QR</strong> i <strong>karta testowa</strong> lasera.</li>
      <li><strong>Dokładne wymiary</strong>: wpisz kerf swojego lasera w warstwie cięcia, a części wyjdą w narysowanym rozmiarze; <strong>Odsunięcie</strong> rysuje obrys wokół kształtu albo w jego środku.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}stamp.png"><img loading="lazy" src="{{ img }}stamp.png" alt="Generator pieczątek: tekst, logo i ramka, odwrócone i odbite"></a></div>
  <div class="text-col">
    <h3>Pieczątki jednym kliknięciem</h3>
    <p>Wybierz typowy rozmiar pieczątki (albo własny), wpisz linie, wybierz czcionkę, logo i ramkę, i naciśnij <strong>Generuj pieczątkę</strong>. Kerfly wypala tło, żeby tekst został wypukły, odbija pieczątkę, żeby odbijała się prawidłowo, i dodaje linię cięcia dookoła. Także <strong>pieczątki okrągłe</strong>: tekst wokół góry i dołu, pierścienie oraz tekst albo logo w środku.</p>
  </div>
</div>

<div class="showcase">
  <div class="shot-col"><a href="{{ img }}site-simulation.png"><img loading="lazy" src="{{ img }}site-simulation.png" alt="Symulacja zadania na stole, w połowie"></a></div>
  <div class="text-col">
    <h3>Zobacz zadanie, zanim zrobi to laser</h3>
    <ul>
      <li><strong>Symulacja</strong> odtwarza całe zadanie na stole: kolejność cięć, przejazdy z wyłączonym laserem, raster i czas.</li>
      <li><strong>Objazd konturu</strong> prowadzi głowicę wokół projektu (prostokątem od najbliższego narożnika), żebyś sprawdził, gdzie będzie cięcie.</li>
      <li>Zapis zadania do pliku EGV albo wysłanie gotowego.</li>
    </ul>
  </div>
</div>

<div class="showcase reverse">
  <div class="shot-col"><a href="{{ img }}site-safety.png"><img loading="lazy" src="{{ img }}site-safety.png" alt="Kształt poza stołem na czerwono, z zablokowanym startem"></a></div>
  <div class="text-col">
    <h3>Chroni Twój laser</h3>
    <ul>
      <li>Kształt wystający poza pole robocze robi się czerwony, a Start jest zablokowany, więc głowica nigdy nie wjedzie w ramę.</li>
      <li>Przed wysłaniem czegokolwiek Kerfly sprawdza, że głowica przez całe zadanie zostaje na stole.</li>
      <li>Pauza i wznowienie tym samym przyciskiem; Stop kończy od razu i prosi o bazowanie przed następnym zadaniem.</li>
    </ul>
  </div>
</div>

<div class="showcase">
  <div class="shot-col small"><a href="{{ img }}laser.png"><img loading="lazy" src="{{ img }}laser.png" alt="Zakładka Laser z połączeniem, bazowaniem, strzałkami i narożnikami"></a></div>
  <div class="text-col">
    <h3>Pełna kontrola maszyny</h3>
    <ul>
      <li>Połączenie, bazowanie, odblokowanie osi, przesuwanie głowicy przyciskami albo Ctrl+strzałkami, do narożników lub środka projektu albo do dowolnego X/Y.</li>
      <li>Projekt zostaje na swoim miejscu na stole albo <strong>podąża za głowicą</strong>: jak wolisz.</li>
      <li>Strzał testowy i moc dla każdej operacji na płytach M3.</li>
    </ul>
  </div>
</div>

## Otwiera Twoje pliki

SVG (z Inkscape albo bez), DXF, G-code i obrazy do graweru rastrowego: PNG, JPG, BMP, TIFF, GIF, WebP. Otwarte pliki SVG i DXF można rozbić na osobne kształty i edytować węzeł po węźle.

## Testowany tak, jak trzeba

Kerfly steruje prawdziwą maszyną z laserem, więc „chyba działa” to za mało:

<div class="features">
  <div class="feature"><h3>Dane dla lasera 1:1</h3><p>Po każdej zmianie dane wysyłane do lasera są porównywane bajt po bajcie ze sprawdzonym oryginałem.</p></div>
  <div class="feature"><h3>Wyklikany jak przez użytkownika</h3><p>Przed każdym wydaniem test sam klika cały program w ponad 270 krokach na ekranie Full HD i po każdym kroku sprawdza, czy okno pokazuje to, co Kerfly naprawdę zrobi.</p></div>
  <div class="feature"><h3>Tysiące losowych sesji</h3><p>Losowe klikanie szuka błędów, których człowiek by nie wymyślił; każdy da się dokładnie powtórzyć.</p></div>
  <div class="feature"><h3>Trzy systemy</h3><p>Każda zmiana jest testowana na czystych komputerach z Windows, Linuksem i macOS, a paczki same się sprawdzają przed publikacją.</p></div>
</div>

<h2 id="pobierz">Pobierz</h2>

<p>Za darmo, bez konta, bez Pythona. <a href="{{ site.repo }}/releases/latest">Najnowsze wydanie</a> ma paczkę dla każdego systemu:</p>

<div class="platforms">
  <div class="platform">
    <h3>Windows 10 / 11</h3>
    <p><code>Kerfly-…-windows-setup.exe</code></p>
    <p>Uruchom instalator; za pierwszym razem zaznacz <em>Zainstaluj sterownik USB lasera K40</em>. Nie jest podpisany, więc Windows może napisać, że ochronił komputer: wybierz <em>Więcej informacji → Uruchom mimo to</em>.</p>
  </div>
  <div class="platform">
    <h3>Linux</h3>
    <p><code>Kerfly-…-x86_64.AppImage</code></p>
    <p>Nadaj prawo uruchamiania i uruchom. Raz zezwól na dostęp do portu USB lasera przez <em>Laser → Zezwól na dostęp do USB lasera…</em> (zapyta o hasło).</p>
  </div>
  <div class="platform">
    <h3>macOS 11+ <span class="tag">wstępna</span></h3>
    <p><code>…-macos-arm64.dmg</code> / <code>…-macos-x86_64.dmg</code></p>
    <p>Procesor Apple albo Intel. Przeciągnij Kerfly do Aplikacji; pierwsze uruchomienie wymaga <em>Otwórz mimo to</em> (<a href="{{ site.repo }}/blob/main/INSTALL_pl.md#macos">jak</a>). Jeszcze nie sprawdzony z laserem: daj znać, jak działa.</p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="{{ site.repo }}/releases/latest">Przejdź do najnowszego wydania</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL_pl.md">Instalacja krok po kroku</a>
</div>

## Pytania

<div class="faq">
<details><summary>Z jakimi laserami działa Kerfly?</summary><p>Z laserami CO2 klasy K40 z płytami sterującymi Lihuiyu z rodziny M2 Nano (M1, M2, M3, B1 i inne): nazwa jest nadrukowana na płycie, np. LASER-M2. Inne sterowniki (Ruida, GRBL) nie są obsługiwane; lasery GRBL są w planach.</p></details>
<details><summary>Czy to naprawdę za darmo?</summary><p>Tak: wolne oprogramowanie na licencji GPL-3.0, bez konta, bez reklam, bez ograniczeń. Kod źródłowy jest na <a href="{{ site.repo }}">GitHubie</a>.</p></details>
<details><summary>Czy potrzebuję Inkscape albo innych programów?</summary><p>Nie. Kerfly sam otwiera pliki SVG. Inkscape jest opcjonalny i potrzebny tylko do tekstu w SVG, który ma być cięty albo grawerowany jako linie.</p></details>
<details><summary>Czy potrzebuję sterownika USB?</summary><p>Na Windows instaluje go instalator, gdy zaznaczysz pole. Na Linuksie wystarczy jedno kliknięcie w Kerfly (Laser → Zezwól na dostęp do USB). macOS nie potrzebuje niczego.</p></details>
<details><summary>Czy Kerfly jest po polsku?</summary><p>Tak, i do tego po angielsku, niemiecku, hiszpańsku i francusku; używa języka systemu, a zmienisz go w Ustawienia → Zaawansowane.</p></details>
<details><summary>Coś nie działa. Co robić?</summary><p>Wybierz w Kerfly Pomoc → Zgłoś problem: program zapisze raport diagnostyczny i otworzy <a href="{{ site.repo }}/issues/new/choose">formularz zgłoszenia</a>. Możesz pisać po polsku.</p></details>
</div>

## Stan projektu

**Kerfly 1.2 jest wersją stabilną, gotową do codziennej pracy** z laserem.
Następne w planach: wektoryzacja obrazów, więcej wzorów,
więcej formatów plików oraz paczka dla Debiana z własnym repozytorium APT.
Zobacz [plan]({{ site.repo }}/blob/main/ROADMAP.md) (po angielsku) i
[listę zmian]({{ site.repo }}/blob/main/CHANGELOG.md).

## Pomoc i uwagi

Coś nie działa? W Kerfly wybierz **Pomoc → Zgłoś problem na GitHubie…**:
program zapisze raport diagnostyczny i otworzy
[formularz zgłoszenia]({{ site.repo }}/issues/new/choose). Formularze są po
angielsku, ale **możesz pisać po polsku**. Pomysły i poprawki tłumaczeń też
są mile widziane.
