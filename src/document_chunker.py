import re
from typing import List, Dict
from datetime import datetime


class DocumentChunker: 
    # Initialize the DocumentChunker with default max tokens
    def __init__(self, max_tokens: int = 450):
        self.metadata = {
            "last_processed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.max_tokens = max_tokens
        self.approx_chars_per_token = 4
        self.max_chars = max_tokens * self.approx_chars_per_token

    # Remove extra spaces and leading/trailing spaces
    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    # Remove heading markers from the text
    def _remove_heading_markers(self, text: str) -> str:
        text = re.sub(r'^#{1,6}\s+', '', text)
        return text.strip()

    # Remove extra newlines and special characters
    def _preprocess_content(self, content: str) -> str:
        content = re.sub(r'\n{2,}', '\n', content)
        content = re.sub(r'\|\s*\n\s*\|', '|\\n|', content)
        content = re.sub(r'\|\s*---\s*\|', '|---|', content)
        return content
    
    # Extract the source from the content
    def _extract_source(self, content: str) -> str:
        match = re.match(r'^#\s+(.+?)(?:\n|$)', content)
        if match:
            return match.group(1).strip()
        return "Unknown Source"

    # Remove the h1 header from the content
    def _remove_h1_header(self, content: str) -> str:
        pattern = r'^#\s+[^\n]+\n+(?=##\s)'
        return re.sub(pattern, '', content)

    # Merge consecutive headings into a single heading
    def _merge_consecutive_headings(self, content: str) -> str:
        pattern = r'(##\s+[^\n]+)\n(###\s+[^\n]+)'
        
        def merge_headings(match):
            h2 = match.group(1)
            h3_text = match.group(2).lstrip('#').strip()
            return f"{h2} | {h3_text}"
        
        return re.sub(pattern, merge_headings, content)

    # Extract the chunk title from the text
    def _extract_chunk_title(self, text: str, section_title: str) -> str:
        match = re.match(r'^(#{2,6})\s+([^\n]+)', text)
        if match:
            return self._remove_heading_markers(match.group(0))
        return section_title

    # Split the text into chunks
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

    # Process the documentation file and return chunks with metadata
    def process_documentation(self, input_path: str) -> List[Dict]:
        with open(input_path, 'r', encoding='utf-8') as file:
            content = file.read()

        from pathlib import Path
        file_prefix = Path(input_path).stem

        # Preprocess content
        content = self._preprocess_content(content)
        document_source = self._extract_source(content)
        content = self._remove_h1_header(content)
        content = self._merge_consecutive_headings(content)
        
        # Split content into sections
        chunks = []
        sections = re.split(r'\n\s*##\s+(?=[A-Za-z0-9])', content)

        # Process each section
        for section_idx, section in enumerate(sections):
            if not section.strip():
                continue

            # Extract section title
            title_match = re.match(r'^([^\n]+)', section)
            raw_title = title_match.group(1) if title_match else "Untitled Section"
            section_title = self._remove_heading_markers(raw_title)

            # Process subsections
            subsections = []
            current_chunk = []

            # Process each line in the section
            for line in section.split('\n'):
                # Process table rows
                if line.startswith('|'):
                    current_chunk.append(line)
                
                # Process subsections
                elif line.startswith('###'):
                    if current_chunk:
                        subsections.append('\n'.join(current_chunk))
                        current_chunk = []
                    current_chunk.append(line)
                
                # Process main sections
                elif line.startswith('##'):
                    if current_chunk:
                        subsections.append('\n'.join(current_chunk))
                        current_chunk = []
                    current_chunk.append(line)
                
                # Process other lines
                else:
                    current_chunk.append(line)
            
            # Add the last chunk
            if current_chunk:
                subsections.append('\n'.join(current_chunk))

            chunk_counter = 0

            # Process each subsection
            for subsection in subsections:
                chunk_title = self._extract_chunk_title(subsection, section_title)
                
                # Clean the subsection content
                cleaned_content = self._clean_text(subsection)
                if not cleaned_content:
                    continue
                
                # Remove heading markers
                cleaned_content = self._remove_heading_markers(cleaned_content)
                
                # Split if exceeds token limit
                content_parts = self._split_long_text(cleaned_content)
                
                # Process each content part
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
