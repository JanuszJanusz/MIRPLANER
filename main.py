import pygame
import sys
import csv
import os
import random
import colorsys
from dataclasses import dataclass, field
from typing import List, Optional

# --- KONFIGURACJA I STAŁE ---
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

# Kolory
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (120, 120, 120)
LIGHT_GRAY = (225, 225, 225)
LIGHT_BLUE = (173, 216, 230)
TEAL = (0, 128, 128)
BG_COLOR = (245, 245, 245)
SCROLLBAR_COLOR = (100, 100, 100)
SCROLLBAR_BG = (200, 200, 200)

# Kolory przycisków
BTN_RESET_BG = (220, 80, 80)
BTN_RESET_HOVER = (200, 50, 50)
BTN_INFO_BG = (70, 130, 180)
BTN_INFO_HOVER = (50, 100, 150)
BTN_TEXT = WHITE

# Ustawienia układu
SIDEBAR_WIDTH = 320
DAYS_COLUMN_WIDTH = 120
GRID_START_X = SIDEBAR_WIDTH + DAYS_COLUMN_WIDTH
GRID_START_Y = 100

# Ustawienia siatki 15-minutowej
START_HOUR = 8
END_HOUR = 20
SLOTS_PER_HOUR = 4
TOTAL_SLOTS = (END_HOUR - START_HOUR) * SLOTS_PER_HOUR
SLOT_WIDTH = 30
SLOT_HEIGHT = 80
DEFAULT_DURATION_SLOTS = 6
GRID_END_PADDING = 100 

DAYS = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek"]

# --- FUNKCJE POMOCNICZE ---
def generuj_czytelny_kolor():
    """Generuje losowy kolor w przestrzeni HSV, który jest wystarczająco ciemny dla białego tekstu."""
    h = random.random() # Barwa (0-1)
    s = random.uniform(0.5, 0.8) # Nasycenie
    v = random.uniform(0.4, 0.7) # Jasność (im ciemniej, tym lepiej widać biały tekst)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

# --- MODELE DANYCH ---
@dataclass
class Przedmiot:
    nazwa: str

@dataclass
class Sala:
    numer: str
    pojemnosc: int

@dataclass
class Nauczyciel:
    imie_nazwisko: str
    specjalizacje: List[str] = field(default_factory=list)

    def czy_prowadzi(self, przedmiot: Przedmiot) -> bool:
        return przedmiot.nazwa in self.specjalizacje

@dataclass
class GrupaStudencka:
    nazwa: str
    liczebnosc: int

@dataclass
class Zajecie:
    przedmiot: Przedmiot
    grupa: GrupaStudencka
    nauczyciel: Nauczyciel
    sala: Sala
    duration_slots: int = DEFAULT_DURATION_SLOTS
    kolor: tuple = TEAL

# --- KLASY INTERFEJSU ---
class DraggableItem:
    def __init__(self, zajecie: Zajecie, home_x: int, home_y: int):
        self.zajecie = zajecie
        w = self.zajecie.duration_slots * SLOT_WIDTH
        h = SLOT_HEIGHT
        self.home_rect = pygame.Rect(home_x, home_y, w, h)
        self.rect = self.home_rect.copy()
        
        self.dragging = False
        self.is_placed = False
        
        self.placed_col = -1
        self.placed_row = -1
        
        self.offset_x = 0
        self.offset_y = 0

    def draw_item(self, surface, font, rect, is_selected=False, is_dragging=False):
        draw_rect = rect.inflate(-4, -4)
        color = self.zajecie.kolor
        
        pygame.draw.rect(surface, color, draw_rect, border_radius=5)
        pygame.draw.rect(surface, BLACK, draw_rect, 1, border_radius=5)
        
        if is_selected:
            pygame.draw.rect(surface, (255, 215, 0), draw_rect, 3, border_radius=5)

        text_color = WHITE if not is_dragging else BLACK
        
        text_str = self.zajecie.przedmiot.nazwa
        if len(text_str) > 18: text_str = text_str[:16] + "..."
        
        text = font.render(text_str, True, text_color)
        text_rect = text.get_rect(center=rect.center)
        surface.blit(text, text_rect)

    def draw_sidebar(self, surface, font, is_selected, scroll_y):
        if self.is_placed and not self.dragging:
            return
        # Przesuwamy tylko widok, nie sam prostokąt
        draw_rect = self.rect.copy()
        draw_rect.y -= scroll_y
        self.draw_item(surface, font, draw_rect, is_selected=is_selected)

    def draw_on_grid(self, surface, font, scroll_x):
        if not self.is_placed or self.dragging:
            return
            
        x = GRID_START_X + self.placed_col * SLOT_WIDTH - scroll_x
        y = GRID_START_Y + self.placed_row * SLOT_HEIGHT
        w = self.zajecie.duration_slots * SLOT_WIDTH
        h = SLOT_HEIGHT
        
        if x + w > GRID_START_X and x < SCREEN_WIDTH:
            rect = pygame.Rect(x, y, w, h)
            self.draw_item(surface, font, rect)

# --- GŁÓWNA GRA ---
class PlannerGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("M.I.R. Planner - Prototyp")
        self.clock = pygame.time.Clock()
        
        self.font_small = pygame.font.SysFont("Arial", 14)
        self.font_medium = pygame.font.SysFont("Arial", 16, bold=True)
        self.font_large = pygame.font.SysFont("Arial", 24, bold=True)

        self.draggable_items: List[DraggableItem] = []
        self.dragged_item: Optional[DraggableItem] = None
        self.selected_item: Optional[DraggableItem] = None

        # Dane
        self.sale: List[Sala] = []
        self.nauczyciele: List[Nauczyciel] = []
        self.przedmioty_dict = {} # Słownik do przypisywania stałych kolorów przedmiotom

        # Stany okienek
        self.show_sale_overlay = False
        self.show_nauczyciele_overlay = False

        # Definicje przycisków
        self.btn_sale_rect = pygame.Rect(250, 20, 100, 40)
        self.btn_nauczyciele_rect = pygame.Rect(370, 20, 140, 40)
        self.reset_btn_rect = pygame.Rect(SCREEN_WIDTH - 180, 20, 160, 40)

        # Przewijanie
        self.scroll_x = 0
        self.max_scroll_x = (TOTAL_SLOTS * SLOT_WIDTH) + GRID_END_PADDING - (SCREEN_WIDTH - GRID_START_X)
        if self.max_scroll_x < 0: self.max_scroll_x = 0
        
        self.sidebar_scroll_y = 0
        self.max_sidebar_scroll_y = 0
        
        self.wczytaj_dane_csv()

    def wczytaj_dane_csv(self):
        # 1. Sale
        if os.path.exists('sale.csv'):
            with open('sale.csv', mode='r', encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    self.sale.append(Sala(numer=row['numer'], pojemnosc=int(row['pojemnosc'])))
        
        # 2. Nauczyciele
        if os.path.exists('nauczyciele.csv'):
            with open('nauczyciele.csv', mode='r', encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    specs = [s.strip() for s in row['specjalizacje'].split(',')]
                    self.nauczyciele.append(Nauczyciel(imie_nazwisko=row['imie_nazwisko'], specjalizacje=specs))

        # 3. Zajęcia
        if os.path.exists('zajecia.csv'):
            with open('zajecia.csv', mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                start_x = (SIDEBAR_WIDTH - (DEFAULT_DURATION_SLOTS * SLOT_WIDTH)) // 2
                
                for idx, row in enumerate(reader):
                    # Pobieranie/ Tworzenie przedmiotu i przypisywanie koloru
                    nazwa_przedmiotu = row['przedmiot']
                    if nazwa_przedmiotu not in self.przedmioty_dict:
                        self.przedmioty_dict[nazwa_przedmiotu] = {
                            'obj': Przedmiot(nazwa_przedmiotu),
                            'kolor': generuj_czytelny_kolor()
                        }
                    przedmiot_obj = self.przedmioty_dict[nazwa_przedmiotu]['obj']
                    kolor_obj = self.przedmioty_dict[nazwa_przedmiotu]['kolor']

                    # Znajdowanie nauczyciela
                    nazwa_nauczyciela = row['nauczyciel']
                    nauczyciel_obj = next((n for n in self.nauczyciele if n.imie_nazwisko == nazwa_nauczyciela), None)
                    if not nauczyciel_obj:
                        nauczyciel_obj = Nauczyciel(nazwa_nauczyciela, [nazwa_przedmiotu])
                        self.nauczyciele.append(nauczyciel_obj)

                    # Znajdowanie sali
                    numer_sali = row['sala']
                    sala_obj = next((s for s in self.sale if s.numer == numer_sali), None)
                    if not sala_obj:
                        sala_obj = Sala(numer_sali, 30)
                        self.sale.append(sala_obj)

                    # Grupa
                    grupa_obj = GrupaStudencka(row['grupa'], 20)

                    # Tworzenie zajęć
                    zajecie = Zajecie(
                        przedmiot=przedmiot_obj,
                        grupa=grupa_obj,
                        nauczyciel=nauczyciel_obj,
                        sala=sala_obj,
                        kolor=kolor_obj
                    )
                    
                    # Obliczanie pozycji Y w panelu (start 100, odstęp 100)
                    y_pos = 100 + idx * 100
                    self.draggable_items.append(DraggableItem(zajecie, start_x, y_pos))

        # Obliczanie maksymalnego przewinięcia panelu bocznego
        if self.draggable_items:
            max_y = max(item.home_rect.bottom for item in self.draggable_items)
            self.max_sidebar_scroll_y = max(0, max_y - SCREEN_HEIGHT + 50) # +50 marginesu na dole

    def reset_plan(self):
        for item in self.draggable_items:
            item.is_placed = False
            item.dragging = False
            item.placed_col = -1
            item.placed_row = -1
            item.rect = item.home_rect.copy()
        
        self.selected_item = None
        self.dragged_item = None

    def can_place(self, target_col: int, target_row: int, duration: int, ignore_item: Optional[DraggableItem] = None) -> bool:
        if target_row < 0 or target_row >= len(DAYS): return False
        if target_col < 0 or target_col + duration > TOTAL_SLOTS: return False

        target_start = target_col
        target_end = target_col + duration

        for item in self.draggable_items:
            if item.is_placed and item != ignore_item:
                if item.placed_row == target_row:
                    item_start = item.placed_col
                    item_end = item.placed_col + item.zajecie.duration_slots
                    
                    if max(item_start, target_start) < min(item_end, target_end):
                        return False
        return True

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.MOUSEWHEEL:
                mouse_x, _ = pygame.mouse.get_pos()
                # Sprawdzanie, gdzie jest myszka, aby przewijać odpowiedni obszar
                if mouse_x < SIDEBAR_WIDTH:
                    self.sidebar_scroll_y -= event.y * 40
                    self.sidebar_scroll_y = max(0, min(self.sidebar_scroll_y, self.max_sidebar_scroll_y))
                else:
                    self.scroll_x -= event.y * 60
                    self.scroll_x = max(0, min(self.scroll_x, self.max_scroll_x))

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mouse_pos = pygame.mouse.get_pos()

                    if self.show_sale_overlay or self.show_nauczyciele_overlay:
                        self.show_sale_overlay = False
                        self.show_nauczyciele_overlay = False
                        continue

                    if self.reset_btn_rect.collidepoint(mouse_pos):
                        self.reset_plan()
                        continue
                    if self.btn_sale_rect.collidepoint(mouse_pos):
                        self.show_sale_overlay = True
                        continue
                    if self.btn_nauczyciele_rect.collidepoint(mouse_pos):
                        self.show_nauczyciele_overlay = True
                        continue

                    # Panel boczny
                    if mouse_pos[0] < SIDEBAR_WIDTH:
                        clicked_any = False
                        for item in reversed(self.draggable_items):
                            # Sprawdzamy kolizję z uwzględnieniem przewinięcia
                            test_rect = item.rect.copy()
                            test_rect.y -= self.sidebar_scroll_y
                            
                            if test_rect.collidepoint(mouse_pos) and not item.is_placed:
                                if self.selected_item == item:
                                    self.selected_item = None
                                else:
                                    self.selected_item = item
                                    self.dragged_item = item
                                    item.dragging = False
                                    self.mouse_down_pos = mouse_pos
                                    item.offset_x = test_rect.x - mouse_pos[0]
                                    item.offset_y = test_rect.y - mouse_pos[1]
                                clicked_any = True
                                break
                        if not clicked_any:
                            self.selected_item = None

                    elif mouse_pos[0] >= GRID_START_X and mouse_pos[1] >= GRID_START_Y:
                        if self.selected_item:
                            target_col = int((mouse_pos[0] - GRID_START_X + self.scroll_x) // SLOT_WIDTH)
                            target_row = int((mouse_pos[1] - GRID_START_Y) // SLOT_HEIGHT)
                            
                            if self.can_place(target_col, target_row, self.selected_item.zajecie.duration_slots):
                                self.selected_item.is_placed = True
                                self.selected_item.placed_col = target_col
                                self.selected_item.placed_row = target_row
                                self.selected_item.rect = self.selected_item.home_rect.copy()
                                self.selected_item = None
                                self.dragged_item = None
                        else:
                            for item in reversed(self.draggable_items):
                                if item.is_placed:
                                    x = GRID_START_X + item.placed_col * SLOT_WIDTH - self.scroll_x
                                    y = GRID_START_Y + item.placed_row * SLOT_HEIGHT
                                    w = item.zajecie.duration_slots * SLOT_WIDTH
                                    h = SLOT_HEIGHT
                                    rect = pygame.Rect(x, y, w, h)
                                    if rect.collidepoint(mouse_pos):
                                        item.is_placed = False
                                        self.selected_item = item
                                        self.dragged_item = item
                                        item.dragging = False
                                        self.mouse_down_pos = mouse_pos
                                        item.rect.width = w
                                        item.rect.height = h
                                        item.rect.x = x
                                        item.rect.y = y
                                        item.offset_x = item.rect.x - mouse_pos[0]
                                        item.offset_y = item.rect.y - mouse_pos[1]
                                        break
                                        
                elif event.button == 3:
                    mouse_pos = pygame.mouse.get_pos()
                    if mouse_pos[0] >= GRID_START_X and mouse_pos[1] >= GRID_START_Y:
                        for item in reversed(self.draggable_items):
                            if item.is_placed:
                                x = GRID_START_X + item.placed_col * SLOT_WIDTH - self.scroll_x
                                y = GRID_START_Y + item.placed_row * SLOT_HEIGHT
                                w = item.zajecie.duration_slots * SLOT_WIDTH
                                h = SLOT_HEIGHT
                                rect = pygame.Rect(x, y, w, h)
                                
                                if rect.collidepoint(mouse_pos):
                                    item.is_placed = False
                                    item.rect = item.home_rect.copy()
                                    if self.selected_item == item: self.selected_item = None
                                    if self.dragged_item == item: self.dragged_item = None
                                    break

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    if self.dragged_item:
                        if self.dragged_item.dragging:
                            mouse_pos = pygame.mouse.get_pos()
                            self.dragged_item.dragging = False
                            
                            if mouse_pos[0] < SIDEBAR_WIDTH:
                                self.dragged_item.rect = self.dragged_item.home_rect.copy()
                                self.dragged_item.is_placed = False
                                self.selected_item = None
                            elif mouse_pos[0] >= GRID_START_X and mouse_pos[1] >= GRID_START_Y:
                                target_col = round((self.dragged_item.rect.x - GRID_START_X + self.scroll_x) / SLOT_WIDTH)
                                target_row = round((self.dragged_item.rect.y - GRID_START_Y) / SLOT_HEIGHT)
                                
                                if self.can_place(target_col, target_row, self.dragged_item.zajecie.duration_slots):
                                    self.dragged_item.is_placed = True
                                    self.dragged_item.placed_col = target_col
                                    self.dragged_item.placed_row = target_row
                                    self.selected_item = None
                                else:
                                    self.dragged_item.rect = self.dragged_item.home_rect.copy()
                                    self.dragged_item.is_placed = False
                                    self.selected_item = None
                            else:
                                self.dragged_item.rect = self.dragged_item.home_rect.copy()
                                self.dragged_item.is_placed = False
                                self.selected_item = None
                        else:
                            if not self.dragged_item.is_placed:
                                self.dragged_item.rect = self.dragged_item.home_rect.copy()
                        
                        self.dragged_item = None

            elif event.type == pygame.MOUSEMOTION:
                if self.dragged_item:
                    mouse_pos = pygame.mouse.get_pos()
                    if not self.dragged_item.dragging:
                        dx = abs(mouse_pos[0] - self.mouse_down_pos[0])
                        dy = abs(mouse_pos[1] - self.mouse_down_pos[1])
                        if dx > 5 or dy > 5:
                            self.dragged_item.dragging = True
                            if self.dragged_item in self.draggable_items:
                                self.draggable_items.remove(self.dragged_item)
                                self.draggable_items.append(self.dragged_item)
                    
                    if self.dragged_item.dragging:
                        self.dragged_item.rect.x = mouse_pos[0] + self.dragged_item.offset_x
                        self.dragged_item.rect.y = mouse_pos[1] + self.dragged_item.offset_y

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.selected_item:
                        if not self.selected_item.is_placed:
                            self.selected_item.rect = self.selected_item.home_rect.copy()
                        self.selected_item = None
                        self.dragged_item = None
                    self.show_sale_overlay = False
                    self.show_nauczyciele_overlay = False

    def draw_sidebar_scrollbar(self):
        if self.max_sidebar_scroll_y > 0:
            bar_x = SIDEBAR_WIDTH - 15
            bar_height = SCREEN_HEIGHT - 100 # Zostawiamy trochę miejsca na górze i dole
            bar_y = 80
            
            pygame.draw.rect(self.screen, SCROLLBAR_BG, (bar_x, bar_y, 10, bar_height), border_radius=5)
            
            handle_height = max(30, bar_height * (bar_height / (bar_height + self.max_sidebar_scroll_y)))
            handle_y = bar_y + (self.sidebar_scroll_y / self.max_sidebar_scroll_y) * (bar_height - handle_height)
            
            pygame.draw.rect(self.screen, SCROLLBAR_COLOR, (bar_x, handle_y, 10, handle_height), border_radius=5)

    def draw_grid_scrollbar(self):
        if self.max_scroll_x > 0:
            bar_width = SCREEN_WIDTH - GRID_START_X - 20
            bar_y = SCREEN_HEIGHT - 20
            
            pygame.draw.rect(self.screen, SCROLLBAR_BG, (GRID_START_X, bar_y, bar_width, 12), border_radius=6)
            
            handle_width = max(40, bar_width * (bar_width / (bar_width + self.max_scroll_x)))
            handle_x = GRID_START_X + (self.scroll_x / self.max_scroll_x) * (bar_width - handle_width)
            
            pygame.draw.rect(self.screen, SCROLLBAR_COLOR, (handle_x, bar_y, handle_width, 12), border_radius=6)

    def draw_grid(self):
        for row_idx in range(len(DAYS)):
            pygame.draw.rect(self.screen, WHITE, (GRID_START_X, GRID_START_Y + row_idx * SLOT_HEIGHT, TOTAL_SLOTS * SLOT_WIDTH, SLOT_HEIGHT))

        for i in range(TOTAL_SLOTS + 1):
            x = GRID_START_X + i * SLOT_WIDTH - self.scroll_x
            if GRID_START_X <= x <= SCREEN_WIDTH:
                if i % SLOTS_PER_HOUR == 0:
                    pygame.draw.line(self.screen, DARK_GRAY, (x, GRID_START_Y), (x, GRID_START_Y + len(DAYS) * SLOT_HEIGHT), 2)
                    hour = START_HOUR + (i // SLOTS_PER_HOUR)
                    text = self.font_small.render(f"{hour:02d}:00", True, BLACK)
                    text_rect = text.get_rect(midleft=(x + 5, GRID_START_Y - 15))
                    self.screen.blit(text, text_rect)
                else:
                    pygame.draw.line(self.screen, LIGHT_GRAY, (x, GRID_START_Y), (x, GRID_START_Y + len(DAYS) * SLOT_HEIGHT), 1)

        for i in range(len(DAYS) + 1):
            y = GRID_START_Y + i * SLOT_HEIGHT
            pygame.draw.line(self.screen, DARK_GRAY, (GRID_START_X, y), (SCREEN_WIDTH, y), 2)

    def draw_top_bar(self):
        mouse_pos = pygame.mouse.get_pos()
        
        color_sale = BTN_INFO_HOVER if self.btn_sale_rect.collidepoint(mouse_pos) else BTN_INFO_BG
        pygame.draw.rect(self.screen, color_sale, self.btn_sale_rect, border_radius=5)
        pygame.draw.rect(self.screen, BLACK, self.btn_sale_rect, 1, border_radius=5)
        txt_sale = self.font_medium.render("Sale", True, BTN_TEXT)
        self.screen.blit(txt_sale, txt_sale.get_rect(center=self.btn_sale_rect.center))

        color_naucz = BTN_INFO_HOVER if self.btn_nauczyciele_rect.collidepoint(mouse_pos) else BTN_INFO_BG
        pygame.draw.rect(self.screen, color_naucz, self.btn_nauczyciele_rect, border_radius=5)
        pygame.draw.rect(self.screen, BLACK, self.btn_nauczyciele_rect, 1, border_radius=5)
        txt_naucz = self.font_medium.render("Nauczyciele", True, BTN_TEXT)
        self.screen.blit(txt_naucz, txt_naucz.get_rect(center=self.btn_nauczyciele_rect.center))

        color_reset = BTN_RESET_HOVER if self.reset_btn_rect.collidepoint(mouse_pos) else BTN_RESET_BG
        pygame.draw.rect(self.screen, color_reset, self.reset_btn_rect, border_radius=5)
        pygame.draw.rect(self.screen, BLACK, self.reset_btn_rect, 1, border_radius=5)
        txt_reset = self.font_medium.render("Resetuj plan", True, BTN_TEXT)
        self.screen.blit(txt_reset, txt_reset.get_rect(center=self.reset_btn_rect.center))

    def draw_overlay(self, title, lines):
        overlay_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay_surface.fill((0, 0, 0, 150))
        self.screen.blit(overlay_surface, (0, 0))

        box_width = 500
        box_height = 400
        box_x = (SCREEN_WIDTH - box_width) // 2
        box_y = (SCREEN_HEIGHT - box_height) // 2
        box_rect = pygame.Rect(box_x, box_y, box_width, box_height)

        pygame.draw.rect(self.screen, WHITE, box_rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, box_rect, 2, border_radius=10)

        title_surf = self.font_large.render(title, True, BLACK)
        self.screen.blit(title_surf, (box_x + 20, box_y + 20))
        pygame.draw.line(self.screen, GRAY, (box_x + 10, box_y + 60), (box_x + box_width - 10, box_y + 60), 2)

        y_offset = box_y + 80
        for line in lines:
            text_surf = self.font_medium.render(line, True, BLACK)
            self.screen.blit(text_surf, (box_x + 20, y_offset))
            y_offset += 30

        close_surf = self.font_small.render("Kliknij gdziekolwiek lub naciśnij ESC, aby zamknąć", True, GRAY)
        self.screen.blit(close_surf, (box_x + 20, box_y + box_height - 30))

    def draw_ui(self):
        self.screen.fill(BG_COLOR)

        # --- LEWY PANEL (Z KLIPOWANIEM I PRZEWIJANIEM) ---
        pygame.draw.rect(self.screen, (230, 235, 240), (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(self.screen, DARK_GRAY, (SIDEBAR_WIDTH, 0), (SIDEBAR_WIDTH, SCREEN_HEIGHT), 2)
        
        title = self.font_large.render("M.I.R. Planner", True, BLACK)
        self.screen.blit(title, (20, 20))
        panel_title = self.font_medium.render("Dostępne zajęcia:", True, BLACK)
        self.screen.blit(panel_title, (20, 70))

        # Klipowanie panelu bocznego (poniżej nagłówka), aby elementy nie nachodziły na tytuł
        sidebar_clip_rect = pygame.Rect(0, 80, SIDEBAR_WIDTH, SCREEN_HEIGHT - 80)
        self.screen.set_clip(sidebar_clip_rect)

        for item in self.draggable_items:
            if not item.is_placed or item.dragging:
                if item.rect.x < SIDEBAR_WIDTH and not item.dragging:
                    item.draw_sidebar(self.screen, self.font_small, is_selected=(item == self.selected_item), scroll_y=self.sidebar_scroll_y)

        self.screen.set_clip(None)
        self.draw_sidebar_scrollbar()

        # --- KOLUMNA DNI ---
        pygame.draw.rect(self.screen, (240, 240, 240), (SIDEBAR_WIDTH, 0, DAYS_COLUMN_WIDTH, SCREEN_HEIGHT))
        pygame.draw.line(self.screen, DARK_GRAY, (GRID_START_X, 0), (GRID_START_X, SCREEN_HEIGHT), 2)
        
        for row_idx, day in enumerate(DAYS):
            day_rect = pygame.Rect(SIDEBAR_WIDTH, GRID_START_Y + row_idx * SLOT_HEIGHT, DAYS_COLUMN_WIDTH, SLOT_HEIGHT)
            pygame.draw.rect(self.screen, (225, 230, 235), day_rect)
            pygame.draw.rect(self.screen, DARK_GRAY, day_rect, 1)
            
            x = SIDEBAR_WIDTH + DAYS_COLUMN_WIDTH // 2
            y = GRID_START_Y + row_idx * SLOT_HEIGHT + SLOT_HEIGHT // 2
            text = self.font_medium.render(day, True, BLACK)
            text_rect = text.get_rect(center=(x, y))
            self.screen.blit(text, text_rect)

        # --- GÓRNA BELKA ---
        self.draw_top_bar()

        # --- OBSZAR SIATKI ---
        grid_clip_rect = pygame.Rect(GRID_START_X, 0, SCREEN_WIDTH - GRID_START_X, SCREEN_HEIGHT)
        self.screen.set_clip(grid_clip_rect)

        self.draw_grid()

        for item in self.draggable_items:
            item.draw_on_grid(self.screen, self.font_small, self.scroll_x)

        if self.selected_item and not self.selected_item.dragging and not self.selected_item.is_placed:
            mouse_pos = pygame.mouse.get_pos()
            if mouse_pos[0] >= GRID_START_X and mouse_pos[1] >= GRID_START_Y:
                target_col = int((mouse_pos[0] - GRID_START_X + self.scroll_x) // SLOT_WIDTH)
                target_row = int((mouse_pos[1] - GRID_START_Y) // SLOT_HEIGHT)
                
                is_valid = self.can_place(target_col, target_row, self.selected_item.zajecie.duration_slots)
                
                x = GRID_START_X + target_col * SLOT_WIDTH - self.scroll_x
                y = GRID_START_Y + target_row * SLOT_HEIGHT
                w = self.selected_item.zajecie.duration_slots * SLOT_WIDTH
                h = SLOT_HEIGHT
                preview_rect = pygame.Rect(x, y, w, h)
                
                if preview_rect.right > GRID_START_X and preview_rect.left < SCREEN_WIDTH:
                    if is_valid:
                        pygame.draw.rect(self.screen, (150, 255, 150), preview_rect, border_radius=5)
                        pygame.draw.rect(self.screen, (0, 200, 0), preview_rect, 2, border_radius=5)
                    else:
                        pygame.draw.rect(self.screen, (255, 150, 150), preview_rect, border_radius=5)
                        pygame.draw.rect(self.screen, (255, 0, 0), preview_rect, 2, border_radius=5)

        self.screen.set_clip(None)

        # Rysowanie przeciąganego elementu na samym wierzchu
        if self.dragged_item and self.dragged_item.dragging:
            self.dragged_item.draw_item(self.screen, self.font_small, self.dragged_item.rect, is_dragging=True)

        self.draw_grid_scrollbar()

        # --- OKIENKA (OVERLAYS) ---
        if self.show_sale_overlay:
            lines = [f"Sala {s.numer} - Pojemność: {s.pojemnosc} os." for s in self.sale]
            self.draw_overlay("Lista Sal", lines)
        elif self.show_nauczyciele_overlay:
            lines = [f"{n.imie_nazwisko} - {', '.join(n.specjalizacje)}" for n in self.nauczyciele]
            self.draw_overlay("Lista Nauczycieli", lines)

    def run(self):
        while True:
            self.handle_events()
            self.draw_ui()
            pygame.display.flip()
            self.clock.tick(FPS)

if __name__ == "__main__":
    game = PlannerGame()
    game.run()