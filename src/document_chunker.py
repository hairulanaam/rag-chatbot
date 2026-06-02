import re
from typing import List, Dict
from src.timezone_utils import now_wib_str


class DocumentChunker: 
    def __init__(self, max_tokens: int = 1840):
        self.metadata = {
            "last_processed": now_wib_str(),
        }
        self.max_tokens = max_tokens
        self.approx_chars_per_token = 4
        self.max_chars = max_tokens * self.approx_chars_per_token

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _remove_heading_markers(self, text: str) -> str:
        text = re.sub(r'^#{1,6}\s+', '', text)
        return text.strip()

    def _preprocess_content(self, content: str) -> str:
        content = re.sub(r'\n{2,}', '\n', content)
        content = re.sub(r'\|\s*\n\s*\|', '|\\n|', content)
        content = re.sub(r'\|\s*---\s*\|', '|---|', content)
        return content
    
    def _extract_source(self, content: str) -> str:
        match = re.match(r'^#\s+(.+?)(?:\n|$)', content)
        if match:
            return match.group(1).strip()
        return "Unknown Source"

    def _remove_h1_header(self, content: str) -> str:
        pattern = r'^#\s+[^\n]+\n+(?=##\s)'
        return re.sub(pattern, '', content)

    def _merge_consecutive_headings(self, content: str) -> str:
        pattern = r'(##\s+[^\n]+)\n(###\s+[^\n]+)'
        
        def merge_headings(match):
            h2 = match.group(1)
            h3_text = match.group(2).lstrip('#').strip()
            return f"{h2} | {h3_text}"
        
        return re.sub(pattern, merge_headings, content)

    def _extract_chunk_title(self, text: str, section_title: str) -> str:
        match = re.match(r'^(#{2,6})\s+([^\n]+)', text)
        if match:
            return self._remove_heading_markers(match.group(0))
        return section_title

    def _split_long_text(self, text: str) -> List[str]:
        if len(text) <= self.max_chars:
            return [text]
        
        parts = []
        current_text = text
        
        while len(current_text) > self.max_chars:
            cut_point = self.max_chars
            
            for delimiter in ['. ', '! ', '? ', '\n']:
                last_delimiter = current_text[:self.max_chars].rfind(delimiter)
                if last_delimiter > self.max_chars * 0.5:
                    cut_point = last_delimiter + len(delimiter)
                    break
            else:
                last_space = current_text[:self.max_chars].rfind(' ')
                if last_space > self.max_chars * 0.5:
                    cut_point = last_space + 1
            
            parts.append(current_text[:cut_point].strip())
            current_text = current_text[cut_point:].strip()
        
        if current_text:
            parts.append(current_text)
        
        return parts

    def process_documentation(self, input_path: str) -> List[Dict]:
        with open(input_path, 'r', encoding='utf-8') as file:
            content = file.read()

        from pathlib import Path
        file_prefix = Path(input_path).stem

        content = self._preprocess_content(content)
        document_source = self._extract_source(content)
        content = self._remove_h1_header(content)
        content = self._merge_consecutive_headings(content)
        
        chunks = []
        sections = re.split(r'\n\s*##\s+(?=[A-Za-z0-9])', content)

        for section_idx, section in enumerate(sections):
            if not section.strip():
                continue

            title_match = re.match(r'^([^\n]+)', section)
            raw_title = title_match.group(1) if title_match else "Untitled Section"
            section_title = self._remove_heading_markers(raw_title)

            subsections = []
            current_chunk = []

            for line in section.split('\n'):
                if line.startswith('|'):
                    current_chunk.append(line)
                
                elif line.startswith('###'):
                    if current_chunk:
                        subsections.append('\n'.join(current_chunk))
                        current_chunk = []
                    current_chunk.append(line)
                
                elif line.startswith('##'):
                    if current_chunk:
                        subsections.append('\n'.join(current_chunk))
                        current_chunk = []
                    current_chunk.append(line)
                
                else:
                    current_chunk.append(line)

            if current_chunk:
                subsections.append('\n'.join(current_chunk))

            chunk_counter = 0

            for subsection in subsections:
                chunk_title = self._extract_chunk_title(subsection, section_title)
                
                cleaned_content = self._clean_text(subsection)
                if not cleaned_content:
                    continue

                cleaned_content = self._remove_heading_markers(cleaned_content)
                
                content_parts = self._split_long_text(cleaned_content)
                
                for part_content in content_parts:
                    chunk = {
                        "id": f"{file_prefix}_section_{section_idx}_chunk_{chunk_counter}",
                        "content": part_content,
                        "metadata": {
                            "source": document_source,
                            "section_title": chunk_title,
                            "sequence": chunk_counter
                        }
                    }
                    chunks.append(chunk)
                    chunk_counter += 1

        print(f"✅ Processed {input_path}: {len(chunks)} chunks created")
        return chunks
