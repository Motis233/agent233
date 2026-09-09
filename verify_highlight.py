"""验证证据图片的高亮是否生效: 检测黄色像素占比"""
from PIL import Image
import os

for img in ["2201.08239_c1_p10.png", "2207.14284_c0_p0.png", "2312.00752_c4_p2.png"]:
    p = os.path.join("evidence", img)
    if not os.path.exists(p):
        print(f"[缺失] {img}")
        continue
    im = Image.open(p).convert("RGB")
    w, h = im.size
    # 抽样统计黄色像素(PyMuPDF高亮默认黄色: R,G高 B低)
    yellow = 0
    total = 0
    for x in range(0, w, 8):
        for y in range(0, h, 8):
            r, g, b = im.getpixel((x, y))
            total += 1
            if r > 200 and g > 180 and b < 150:
                yellow += 1
    print(f"{img}: {w}x{h}, 黄色像素 {yellow}/{total} "
          f"({yellow * 100 / total:.2f}%) "
          f"{'✓ 高亮存在' if yellow > 5 else '✗ 无高亮!'}")
