import os
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
import re

def translate_text(text: str) -> str:
    """Translate English text to Chinese with common UML/diagram terms"""
    translations = {
        "Home": "首页",
        "All Diagrams": "所有图表",
        "Index": "索引",
        "Navigation": "导航",
        "Untitled": "未命名",
        "Main": "主图",
        "Sequence Diagram": "时序图",
        "Flowchart Diagram": "流程图",
        "Statechart Diagram": "状态图",
        "ER Diagram": "ER图",
        "Mindmap Diagram": "思维导图",
        "Class Diagram": "类图",
        "by Mermaid": "由 Mermaid 生成",
        "Frame Alert": "框架提示",
        "This document is designed to be viewed using the frames feature.": "本文档需要在支持框架的浏览器中查看。",
        "If you see this message, you are using a non-frame-capable web client.": "如果您看到此消息，说明您的浏览器不支持框架功能。",
        "Link to": "链接到",
        "Non-frame version": "非框架版本",
    }
    
    # Apply translations in a specific order to handle longer phrases first
    sorted_translations = sorted(translations.items(), key=lambda x: len(x[0]), reverse=True)
    for en, zh in sorted_translations:
        text = text.replace(en, zh)
    
    return text

def translate_html_file(input_path: str, output_path: str = None):
    """Translate HTML file preserving structure"""
    try:
        if output_path is None:
            output_path = input_path
        
        # Read the file
        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # Translate text nodes
        for element in soup.find_all(text=True):
            if element.parent.name not in ['script', 'style']:
                if isinstance(element, NavigableString):
                    translated = translate_text(str(element))
                    element.replace_with(translated)
        
        # Translate title and alt attributes
        for tag in soup.find_all(attrs={"title": True}):
            tag['title'] = translate_text(tag['title'])
        
        for tag in soup.find_all(attrs={"alt": True}):
            tag['alt'] = translate_text(tag['alt'])
        
        # Write back with preserved formatting
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))
            
    except FileNotFoundError:
        print(f"Error: File not found - {input_path}")
    except Exception as e:
        print(f"Error translating {input_path}: {str(e)}")

def main():
    try:
        base_dir = Path("/Users/kim/Downloads/lolbot/html-docs")
        
        if not base_dir.exists():
            print(f"Error: Base directory does not exist - {base_dir}")
            return
            
        # Translate main files
        main_files = [
            base_dir / "index.html",
            base_dir / "contents" / "navigation.html",
            base_dir / "contents" / "diagrams.html",
            base_dir / "contents" / "element_index.html",
        ]
        
        for file in main_files:
            if file.exists():
                print(f"Translating {file.name}...")
                translate_html_file(str(file))
            else:
                print(f"Warning: File not found - {file.name}")
        
        # Translate all content HTML files
        contents_dir = base_dir / "contents"
        if contents_dir.exists():
            for html_file in contents_dir.glob("*.html"):
                if html_file.name not in ["navigation.html", "diagrams.html", "element_index.html"]:
                    print(f"Translating {html_file.name}...")
                    translate_html_file(str(html_file))
        else:
            print(f"Error: Contents directory does not exist - {contents_dir}")
            
        print("Translation complete!")
        
    except Exception as e:
        print(f"Error in main process: {str(e)}")

if __name__ == "__main__":
    main()