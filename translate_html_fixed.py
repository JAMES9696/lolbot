import os
import re
import shutil
import logging

TRANSLATIONS = {
    "Navigation": "导航",
    "All Diagrams": "所有图表", 
    "Index": "索引",
    "Home": "首页",
    "Untitled": "未命名",
    "Main": "主图",
    "Sequence Diagram by Mermaid": "时序图 由 Mermaid 生成",
    "Flowchart Diagram by Mermaid": "流程图 由 Mermaid 生成",
    "Statechart Diagram by Mermaid": "状态图 由 Mermaid 生成",
    "ER Diagram by Mermaid": "ER图 由 Mermaid 生成",
    "Mindmap Diagram by Mermaid": "思维导图 由 Mermaid 生成",
    "Class Diagram by Mermaid": "类图 由 Mermaid 生成",
    "Data Model by Mermaid": "数据模型 由 Mermaid 生成",
    "Frame Alert": "框架提示",
    "This document is designed to be viewed using the frames feature.": "本文档需要在支持框架的浏览器中查看。",
    "If you see this message, you are using a non-frame-capable web client.": "如果您看到此消息，说明您的浏览器不支持框架功能。",
    "Link to": "链接到",
    "Non-frame version.": "非框架版本。",
}

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def backup_file(filepath):
    backup_path = filepath + '.backup'
    try:
        shutil.copy2(filepath, backup_path)
        logging.info(f"Backed up {filepath} to {backup_path}")
    except Exception as e:
        logging.error(f"Failed to backup {filepath}: {e}")
        raise

def translate_html_text(content):
    def replace_text(match):
        original_text = match.group(0)
        stripped_text = original_text.strip()
        if stripped_text in TRANSLATIONS:
            translated = TRANSLATIONS[stripped_text]
            leading_whitespace = original_text[:len(original_text) - len(original_text.lstrip())]
            trailing_whitespace = original_text[len(original_text.rstrip()):]
            return leading_whitespace + translated + trailing_whitespace
        return original_text

    try:
        text_pattern = r'(?<=>)[^<]*?(?=<)'
        translated_content = re.sub(text_pattern, replace_text, content)
        logging.info("Text translation completed")
        return translated_content
    except Exception as e:
        logging.error(f"Error during text translation: {e}")
        raise

def process_html_file(filepath):
    try:
        logging.info(f"Processing file: {filepath}")
        backup_file(filepath)
        
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        
        translated_content = translate_html_text(content)
        
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(translated_content)
            
        logging.info(f"Successfully processed {filepath}")
    except Exception as e:
        logging.error(f"Error processing {filepath}: {e}")
        raise

def main():
    setup_logging()
    html_files = []
    
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.html'):
                html_files.append(os.path.join(root, file))
    
    logging.info(f"Found {len(html_files)} HTML files")
    
    for filepath in html_files:
        try:
            process_html_file(filepath)
        except Exception:
            logging.error(f"Skipping {filepath} due to error")

if __name__ == "__main__":
    main()