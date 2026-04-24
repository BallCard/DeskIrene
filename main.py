"""艾丽妮桌面宠物 - 图片加载版"""

import sys
import os
import random

# 把 libs 加入搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "libs"))

from PyQt5.QtWidgets import QApplication, QWidget, QMenu
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QPixmap, QBitmap, QImage, QColor, QRegion

# ─── 路径配置 ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BASE_DIR, "sprites")

# ─── 全局配置 ───
DISPLAY_SCALE = 2.5       # 128px -> ~320px 显示
STATE_CHANGE_MIN = 3000    # 状态最短持续 ms
STATE_CHANGE_MAX = 8000    # 状态最长持续 ms
ALPHA_THRESHOLD = 30       # alpha 低于此值视为透明

# ─── 动画状态定义 ───
STATE_LABELS = {
    "idle":  "待机",
    "walk":  "走路",
    "sit":   "坐下",
    "sleep": "睡觉",
    "wave":  "招手",
    "sword": "战斗",
    "eat":   "吃东西",
    "read":  "看书",
}

ANIMATION_STATES = {
    "idle":  {"file": "idle.png",  "speed": 600},
    "walk":  {"file": "walk.png",  "speed": 400},
    "sit":   {"file": "sit.png",   "speed": 800},
    "sleep": {"file": "sleep.png", "speed": 1000},
    "wave":  {"file": "wave.png",  "speed": 500},
    "sword": {"file": "sword.png", "speed": 350},
    "eat":   {"file": "eat.png",   "speed": 500},
    "read":  {"file": "read.png",  "speed": 600},
}

STATE_LIST = list(ANIMATION_STATES.keys())
STATE_WEIGHTS = [3, 1.5, 1, 1, 1, 1, 1, 1]


def clean_alpha(pix, threshold=ALPHA_THRESHOLD):
    """去除半透明边缘像素"""
    img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() < threshold:
                img.setPixelColor(x, y, QColor(0, 0, 0, 0))
    return QPixmap.fromImage(img)


def pixmap_to_mask(pix):
    """从 QPixmap 生成 QRegion 作为窗口 mask"""
    img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
    # 创建一个与图片同大小的 region
    region = QRegion()
    # 逐行扫描，收集不透明像素组成的矩形条
    for y in range(img.height()):
        x_start = -1
        for x in range(img.width()):
            opaque = img.pixelColor(x, y).alpha() >= ALPHA_THRESHOLD
            if opaque and x_start < 0:
                x_start = x
            elif not opaque and x_start >= 0:
                region = region.united(QRegion(x_start, y, x - x_start, 1))
                x_start = -1
        if x_start >= 0:
            region = region.united(QRegion(x_start, y, img.width() - x_start, 1))
    return region


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()

        # 加载所有精灵图（清理半透明边 + 预计算缩放版和 mask）
        self.sprites = {}
        self.scaled_sprites = {}
        self.sprite_masks = {}

        for state_name, state_data in ANIMATION_STATES.items():
            path = os.path.join(SPRITE_DIR, state_data["file"])
            pix = QPixmap(path)
            if not pix.isNull():
                pix = clean_alpha(pix)
            self.sprites[state_name] = pix

        # 动画状态
        self.current_state = "idle"

        # 微动画参数
        self.breath_offset = 0
        self.breath_dir = 1
        self.sway_offset = 0
        self.sway_dir = 1

        # 窗口属性
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # 计算大小
        sample = self.sprites.get("idle")
        self.base_w = sample.width() if sample and not sample.isNull() else 128
        self.base_h = sample.height() if sample and not sample.isNull() else 128
        self.display_w = int(self.base_w * DISPLAY_SCALE)
        self.display_h = int(self.base_h * DISPLAY_SCALE)

        # 预计算所有状态的缩放图和 mask
        self._build_scaled_cache()

        # 设置初始 mask
        self._apply_mask()

        # 窗口大小固定
        self.setFixedSize(self.display_w, self.display_h)

        # 拖拽
        self._drag_pos = None

        # 帧定时器
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.tick)
        self.frame_timer.start(50)

        # 状态切换定时器
        self.state_timer = QTimer(self)
        self.state_timer.timeout.connect(self.random_state_change)
        self.schedule_state_change()

        self.show()

    def _build_scaled_cache(self):
        """预计算缩放后的 pixmap 和对应 mask"""
        for state_name, pix in self.sprites.items():
            if pix.isNull():
                continue
            scaled = pix.scaled(
                self.display_w, self.display_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            # 缩放后再次清理边缘（SmoothTransformation 可能产生新的半透明像素）
            scaled = clean_alpha(scaled)
            self.scaled_sprites[state_name] = scaled
            self.sprite_masks[state_name] = pixmap_to_mask(scaled)

    def _apply_mask(self):
        """把窗口形状裁剪成当前角色的轮廓"""
        mask = self.sprite_masks.get(self.current_state)
        if mask:
            self.setMask(mask)

    def schedule_state_change(self):
        delay = random.randint(STATE_CHANGE_MIN, STATE_CHANGE_MAX)
        self.state_timer.start(delay)

    def tick(self):
        self.breath_offset += self.breath_dir * 0.3
        if abs(self.breath_offset) > 3:
            self.breath_dir *= -1

        self.sway_offset += self.sway_dir * 0.15
        if abs(self.sway_offset) > 2:
            self.sway_dir *= -1

        self.update()

    def random_state_change(self):
        self.current_state = random.choices(
            STATE_LIST, weights=STATE_WEIGHTS, k=1
        )[0]
        self._apply_mask()
        self.state_timer.stop()
        self.schedule_state_change()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        pix = self.scaled_sprites.get(self.current_state)
        if not pix or pix.isNull():
            painter.end()
            return

        x = int(self.sway_offset)
        y = int(self.breath_offset)
        painter.drawPixmap(x, y, pix)
        painter.end()

    # ─── 鼠标交互 ───
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
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: rgba(74, 111, 165, 0.5);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255,255,255,0.1);
                margin: 4px 8px;
            }
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
            self.update()


def main():
    app = QApplication(sys.argv)
    pet = PetWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
