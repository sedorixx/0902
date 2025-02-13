from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size=(192, 192), color="#0d6efd", output_path="static/icons/icon-192x192.png"):
    # Erstelle ein neues Bild mit transparentem Hintergrund
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Zeichne einen ausgefüllten Kreis
    circle_padding = 10
    circle_bounds = [circle_padding, circle_padding, size[0]-circle_padding, size[1]-circle_padding]
    draw.ellipse(circle_bounds, fill=color)
    
    # Zeichne "PDF" in weiß
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    text = "PDF"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2
    draw.text((x, y), text, fill="white", font=font)
    
    # Speichere das Icon
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")

if __name__ == "__main__":
    create_icon()
