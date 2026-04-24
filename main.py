"""艾丽妮桌面宠物 - 图片加载版"""

import sys
import os
import random
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs"))

from PyQt5.QtWidgets import QApplication, QWidget, QMenu
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap, QBitmap, QImage, QColor

# ─── 配置 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BASE_DIR, "sprites")
DISPLAY_SCALE = 2.5
STATE_CHANGE_MIN = 3000
STATE_CHANGE_MAX = 8000

STATE_LABELS = {
    "idle": "待机", "walk": "走路", "sit": "坐下", "sleep": "睡觉",
    "wave": "招手", "sword": "战斗", "eat": "吃东西", "read": "看书",
}

ANIMATION_STATES = {
    "idle":  {"file": "idle.png"},   "walk":  {"file": "walk.png"},
    "sit":   {"file": "sit.png"},    "sleep": {"file": "sleep.png"},
    "wave":  {"file": "wave.png"},   "sword": {"file": "sword.png"},
    "eat":   {"file": "eat.png"},    "read":  {"file": "read.png"},
}

STATE_LIST = list(ANIMATION_STATES.keys())
STATE_WEIGHTS = [3, 1.5, 1, 1, 1, 1, 1, 1]


def _sample_bg_color(img):
    """采样角落像素，返回平均背景色"""
    w, h = img.width(), img.height()
    corners = [(0,0), (1,0), (0,1), (w-1,h-1), (w-2,h-1), (w-1,h-2),
               (10,0), (0,10), (w//2,0), (0,h//2)]
    r_sum = g_sum = b_sum = count = 0
    for x, y in corners:
        c = img.pixelColor(x, y)
        r_sum += c.red(); g_sum += c.green(); b_sum += c.blue()
        count += 1
    return QColor(r_sum // count, g_sum // count, b_sum // count)


def clean_alpha(pix, tolerance=18):
    """从边缘 flood fill 清除背景，保留角色内部浅色"""
    img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    bg = _sample_bg_color(img)
    transparent = QColor(0, 0, 0, 0)

    # 判断像素是否接近背景色
    def is_bg(x, y):
        c = img.pixelColor(x, y)
        return (abs(c.red() - bg.red()) < tolerance and
                abs(c.green() - bg.green()) < tolerance and
                abs(c.blue() - bg.blue()) < tolerance)

    # BFS 从四条边开始，只清除与边缘连通的背景
    from collections import deque
    visited = set()
    queue = deque()
    for x in range(w):
        for y in [0, h - 1]:
            if is_bg(x, y):
                queue.append((x, y))
                visited.add((x, y))
    for y in range(h):
        for x in [0, w - 1]:
            if is_bg(x, y) and (x, y) not in visited:
                queue.append((x, y))
                visited.add((x, y))

    while queue:
        cx, cy = queue.popleft()
        img.setPixelColor(cx, cy, transparent)
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                visited.add((nx, ny))
                if is_bg(nx, ny):
                    queue.append((nx, ny))

    return QPixmap.fromImage(img)


def make_mask_from_pixmap(pix):
    """从 QPixmap 的 alpha 通道生成 QBitmap mask"""
    img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    alpha_mask = img.createAlphaMask(Qt.ThresholdDither)
    if alpha_mask.isNull():
        return QBitmap()
    return QBitmap.fromImage(alpha_mask)


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()

        # 窗口属性（必须在加载图片前设置）
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        # 加载、缩放、生成 mask
        self.current_state = "idle"
        self.scaled_sprites = {}

        # 用第一张图确定显示尺寸
        first_path = os.path.join(SPRITE_DIR, ANIMATION_STATES["idle"]["file"])
        first_pix = QPixmap(first_path)
        self.base_w = first_pix.width() if not first_pix.isNull() else 128
        self.base_h = first_pix.height() if not first_pix.isNull() else 128
        self.display_w = int(self.base_w * DISPLAY_SCALE)
        self.display_h = int(self.base_h * DISPLAY_SCALE)

        for state_name, state_data in ANIMATION_STATES.items():
            path = os.path.join(SPRITE_DIR, state_data["file"])
            pix = QPixmap(path)
            if pix.isNull():
                continue
            # 缩放
            scaled = pix.scaled(
                self.display_w, self.display_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # 清除 AI 生图残留的低 alpha 背景像素
            cleaned = clean_alpha(scaled)
            self.scaled_sprites[state_name] = cleaned

        self.setFixedSize(self.display_w, self.display_h)
        self._drag_pos = None

        # 帧定时器
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update)
        self.frame_timer.start(80)

        # 状态切换定时器
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.random_state_change)
        self.schedule_state_change()

        self.show()
        # show() 之后设置 mask 才生效
        self._apply_mask()

    def _apply_mask(self):
        """用 createAlphaMask 生成精确的窗口裁剪"""
        pix = self.scaled_sprites.get(self.current_state)
        if pix and not pix.isNull():
            mask = make_mask_from_pixmap(pix)
            if not mask.isNull():
                self.setMask(mask)

    def schedule_state_change(self):
        delay = random.randint(STATE_CHANGE_MIN, STATE_CHANGE_MAX)
        self.state_timer.start(delay)

    def random_state_change(self):
        self.current_state = random.choices(
            STATE_LIST, weights=STATE_WEIGHTS, k=1
        )[0]
        self._apply_mask()
        self.state_timer.stop()
        self.schedule_state_change()

    def paintEvent(self, event):
        painter = QPainter(self)
        # 先用透明色填充整个画布，防止残留
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        pix = self.scaled_sprites.get(self.current_state)
        if not pix or pix.isNull():
            painter.end()
            return
        painter.drawPixmap(0, 0, pix)
        painter.end()

    # ─── 拖拽 ───
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        elif event.button() == Qt.RightButton:
            self.show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None

    # ─── 右键菜单 ───
    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(30, 35, 55, 0.92);
                color: #e0e0e0;
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                padding: 6px 2px;
                font-size: 13px;
            }
            QMenu::item { padding: 6px 24px; border-radius: 4px; }
            QMenu::item:selected { background: rgba(74, 111, 165, 0.5); }
            QMenu::separator { height: 1px; background: rgba(255,255,255,0.1); margin: 4px 8px; }
        """)
        for state in STATE_LIST:
            label = STATE_LABELS.get(state, state)
            action = menu.addAction(f"切换: {label}")
            action.setData(state)
        menu.addSeparator()
        quit_action = menu.addAction("退出")

        action = menu.exec_(pos)
        if action == quit_action:
            QApplication.quit()
        elif action and action.data():
            self.current_state = action.data()
            self._apply_mask()
            self.state_timer.stop()
            self.schedule_state_change()


def main():
    app = QApplication(sys.argv)
    pet = PetWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
