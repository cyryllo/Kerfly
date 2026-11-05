---
layout: default
lang: pl
title: Kerfly po polsku
other_lang: index.html
description: Kerfly to darmowy program do sterowania laserami CO2 K40 z płytami Lihuiyu M2 Nano. Rysuj, układaj i tnij w Linuksie i Windows.
---

<div class="hero">
  <img src="{{ '/assets/logo.svg' | relative_url }}" alt="Logo Kerfly">
  <div>
    <h1>Kerfly</h1>
    <p>Darmowy program do sterowania laserami K40, dla Linuksa i Windows.</p>
  </div>
</div>

<div class="buttons">
  <a class="button primary" href="{{ site.repo }}/releases/latest">Pobierz</a>
  <a class="button" href="{{ '/pl/guide.html' | relative_url }}">Instrukcja obsługi</a>
  <a class="button" href="{{ site.repo }}/blob/main/INSTALL_pl.md">Instalacja</a>
  <a class="button" href="{{ site.repo }}">Kod źródłowy</a>
</div>

<div class="shot"><img src="{{ '/screenshot_pl.png' | relative_url }}" alt="Główne okno Kerfly z rysunkiem na stole lasera"></div>

Kerfly steruje laserami CO2 klasy K40 z **płytami Lihuiyu** (rodzina M2 Nano:
M1, M2, M3, B1, …), czyli popularnymi niebiesko-białymi laserami biurkowymi
sprzedawanymi pod wieloma nazwami. Powstał z **[K40 Whisperera](https://www.scorchworks.com/K40whisperer/k40whisperer.html)**
autorstwa Scorcha i zachowuje jego sterowanie laserem bez zmian: dane
wysyłane do lasera są po każdej zmianie porównywane bajt w bajt z K40
Whispererem. Wokół tego rdzenia Kerfly dodaje nowoczesne okno z narzędziami
do rysowania i edycji.

## Co potrafi

<div class="features">
  <div class="feature"><h3>Układanie na stole</h3><p>Kilka plików naraz na stole lasera: przesuwanie, skalowanie i obracanie myszą albo wpisanymi wartościami, wyrównywanie, grupowanie i kolejność. Cofanie i ponawianie wszystkiego.</p></div>
  <div class="feature"><h3>Rysowanie i edycja</h3><p>Prostokąty, elipsy, wielokąty, linie, krzywe, rysowanie odręczne i tekst dowolną zainstalowaną czcionką, także wzdłuż krzywej albo okręgu. Edycja węzłów narysowanych kształtów i otwartych plików SVG oraz DXF.</p></div>
  <div class="feature"><h3>Warstwy jak w LightBurnie</h3><p>Grawer rastrowy, obrys i cięcie, każde z własną prędkością, liczbą przejść i mocą. Baza materiałów ustawia wszystko jednym wyborem.</p></div>
  <div class="feature"><h3>Wiele formatów</h3><p>SVG (z Inkscape albo bez), DXF, G-code i obrazy: PNG, JPG, BMP, TIFF, GIF, WebP. Projekt trzyma wszystko w jednym pliku.</p></div>
  <div class="feature"><h3>Wzory, mostki, kształty</h3><p>Wypełnianie kształtów grawerowanymi wzorami (fale, plaster miodu, cegły…), a ich obrys nadal jest cięty; mostki trzymające wycięte elementy w arkuszu; łączenie kształtów (suma, różnica, część wspólna).</p></div>
  <div class="feature"><h3>Bezpieczna praca</h3><p>Najpierw objazd konturu, symulacja zadania, szacowany czas. Kerfly nie wyśle zadania, które wyprowadziłoby głowicę poza stół.</p></div>
  <div class="feature"><h3>Jak w K40 Whisperer, jeśli chcesz</h3><p>Ten sam plik ustawień. Projekt może podążać za głowicą albo zostać na swoim miejscu na stole: wybór należy do Ciebie.</p></div>
  <div class="feature"><h3>Po polsku</h3><p>Polski, angielski, niemiecki, hiszpański i francuski. Działa w Linuksie (Debian, Ubuntu) i Windows 10 / 11.</p></div>
</div>

## Jak zacząć

<ol class="steps">
  <li><a href="{{ site.repo }}/releases/latest">Pobierz</a> najnowszą wersję (Source code, zip) i rozpakuj ją.</li>
  <li>Windows: zainstaluj Pythona i sterownik USB; Linux: dodaj regułę USB. <a href="{{ site.repo }}/blob/main/INSTALL_pl.md">Instrukcja instalacji</a> opisuje każdy krok.</li>
  <li>Uruchom <code>start_kerfly.bat</code> (Windows) albo <code>./start_kerfly.sh</code> (Linux). Pierwsze uruchomienie wszystko przygotuje.</li>
  <li>Przeczytaj <a href="{{ '/pl/guide.html' | relative_url }}">instrukcję obsługi</a>: połącz laser, ułóż projekt, objedź kontur, start.</li>
</ol>

## Stan projektu

Kerfly jest we **wczesnej fazie rozwoju**. Pierwszy test na prawdziwym laserze
odbył się w listopadzie 2026 (Windows 10, płyta M3): cięcie trzymało
wymiary, strzałki, pauza i stop działały, a znalezione problemy poprawiła
wersja 0.15. Następne w planach: zawiasy giętkie, wektoryzacja obrazów,
kompensacja kerfu, więcej formatów plików oraz instalatory dla Windows i
Linuksa. Zobacz [plan]({{ site.repo }}/blob/main/ROADMAP.md) (po angielsku) i
[listę zmian]({{ site.repo }}/blob/main/CHANGELOG.md).

## Pomoc i uwagi

Coś nie działa? W Kerfly wybierz **Pomoc → Zgłoś problem na GitHubie…**:
program zapisze raport diagnostyczny i otworzy
[formularz zgłoszenia]({{ site.repo }}/issues/new/choose). Formularze są po
angielsku, ale **możesz pisać po polsku**. Pomysły i poprawki tłumaczeń też
są mile widziane.
