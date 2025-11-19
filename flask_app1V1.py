from flask import Flask, request, render_template
import os
import tempfile
import traceback

from pdf2image import convert_from_path
from paddleocr import PaddleOCR
from rapidfuzz import fuzz

app = Flask(__name__, template_folder='templates')

# Initialize PaddleOCR (only once)
ocr_model = PaddleOCR(use_angle_cls=True, lang='en', det_db_box_thresh=0.2)

# Converts PDF to image
def convert_pdf_to_image(pdf_path):
    images = convert_from_path(pdf_path)
    image_path = pdf_path.replace(".pdf", ".jpg")
    images[0].save(image_path, "JPEG")
    return image_path

# Extract fields using PaddleOCR layout logic
def extract_fields_paddleocr(image_path, fields_to_extract):
    result = ocr_model.ocr(image_path)

    detected_text = []
    for line in result[0]:
        text = line[1][0].strip()
        box = line[0]
        detected_text.append({
            "text": text,
            "box": box
        })

    fields = [field.strip().lower() for field in fields_to_extract.split(',')]
    extracted = {}

    for field in fields:
        best_score = 0
        best_value = "N/A"

        for i, item in enumerate(detected_text):
            score = fuzz.partial_ratio(field, item["text"].lower())
            if score > best_score and score > 80:
                best_score = score
                if i + 1 < len(detected_text):
                    best_value = detected_text[i + 1]["text"]

        extracted[field] = best_value

    return extracted

@app.route('/', methods=['GET'])
def upload_form():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
def compare():
    try:
        file1 = request.files.get('pdf_file1')
        file2 = request.files.get('pdf_file2')
        doc_type = request.form.get('doc_type', '').strip()
        stage = request.form.get('stage')
        doc_type_type = request.form.get('type')

        if not file1 or not file2 or not doc_type:
            return render_template('result.html', error="Both PDFs and a document type must be provided")

        # Update mapping as per your needs
        fields_to_extract_mapping = {
            ('Technical Sanction', 'For Migration', 'Technical Sanction copy'):
                "Name of Work, Est. Value"
        }

        fields_to_extract = fields_to_extract_mapping.get((stage, doc_type_type, doc_type), "")
        if not fields_to_extract:
            return render_template('result.html', error="Invalid Document Type selection.")

        # Save uploaded PDFs
        path1 = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        path2 = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        file1.save(path1)
        file2.save(path2)

        # Convert to images
        img1 = convert_pdf_to_image(path1)
        img2 = convert_pdf_to_image(path2)

        # Extract text using PaddleOCR
        data1 = extract_fields_paddleocr(img1, fields_to_extract)
        data2 = extract_fields_paddleocr(img2, fields_to_extract)

        # Compare fields
        comparison = {}
        scores = []

        for field in data1:
            val1 = data1.get(field, "")
            val2 = data2.get(field, "")
            score = fuzz.ratio(val1.lower(), val2.lower()) if val1 and val2 else 0
            scores.append(score)
            comparison[field] = {
                "doc1": val1,
                "doc2": val2,
                "score": score
            }

        avg_score = round(sum(scores) / len(scores), 2) if scores else 0
        return render_template('result.html', comparison=comparison, match_percentage=avg_score)

    except Exception as e:
        traceback.print_exc()
        return render_template('result.html', error=f"Internal error occurred: {str(e)}")

    finally:
        for file_path in [path1, path2]:
            if os.path.exists(file_path):
                os.remove(file_path)
            image_path = file_path.replace(".pdf", ".jpg")
            if os.path.exists(image_path):
                os.remove(image_path)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=True)
