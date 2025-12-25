#!/usr/bin/env python3
import json
import os
import re
import unicodedata
from pathlib import Path

def main():
    # Пути
    input_file = "wiki_cinema/docs.jsonl"
    output_dir = "../corpus"  # на уровень выше, рядом с corpus_builder
    docs_per_file = 1000
    
    # Проверка файла
    if not os.path.exists(input_file):
        print(f"Ошибка: {input_file} не найден")
        print("Запускай из папки corpus_builder")
        print(f"Текущая папка: {os.getcwd()}")
        return
    
    # Создаем папку для корпуса
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # Удаляем старые файлы корпуса (чистая генерация без резервных копий)
    try:
        for old in Path(output_dir).glob('part_*.tsv'):
            try:
                old.unlink()
            except Exception:
                pass
        for fname in ('info.txt', 'duplicates.log'):
            p = Path(output_dir) / fname
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        print(f"Existing corpus files removed from {output_dir}")
    except Exception:
        # если не удалось удалить – продолжим, но предупредим
        print(f"Warning: could not fully clean {output_dir}")
    
    # Статистика
    total_input_docs = 0   # all documents seen in input
    written_docs = 0       # unique documents written to output
    total_raw_bytes = 0
    total_text_bytes = 0
    file_count = 0
    current_file = None
    seen_ids = set()
    duplicates_log_path = f"{output_dir}/duplicates.log"
    dup_log = open(duplicates_log_path, 'w', encoding='utf-8')
    
    print(f"Читаю {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                
                total_raw_bytes += len(line.encode('utf-8'))
                doc = json.loads(line)
                
                # Новый файл: исходим из количества УНИКАЛЬНЫХ записей, чтобы избежать
                # дубликатов в разных частях из-за пропуска
                if written_docs % docs_per_file == 0:
                    if current_file:
                        current_file.close()

                    file_count += 1
                    filename = f"{output_dir}/part_{file_count:03d}.tsv"
                    current_file = open(filename, 'w', encoding='utf-8')
                    current_file.write("id\ttitle\ttext\n")
                
                # Текст
                def normalize_text(s: str) -> str:
                    if s is None:
                        return ''
                    # Unicode normalization
                    s = unicodedata.normalize('NFC', s)

                    # Replace various no-break spaces and similar with normal space
                    s = s.replace('\u00A0', ' ')  # NO-BREAK SPACE
                    s = s.replace('\u202F', ' ')  # NARROW NO-BREAK SPACE
                    s = s.replace('\uFEFF', '')   # ZERO WIDTH NO-BREAK SPACE (BOM)

                    # Remove soft hyphen and zero-width chars
                    s = s.replace('\u00AD', '')
                    for ch in ('\u200B', '\u200C', '\u200D'):
                        s = s.replace(ch, '')

                    # Normalize various hyphen/dash characters to simple hyphen
                    # en dash 	6, em dash 	7 etc. Cover common variants
                    s = re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]', '-', s)

                    # Remove other control characters except line breaks (keep \n and \r for now)
                    # Category Cc are control chars; preserve \n and \r
                    s = ''.join(ch for ch in s if (unicodedata.category(ch) != 'Cc' or ch in '\n\r'))

                    # Dehyphenation: join pieces split by hyphen at end of line
                    # e.g. 'слово-\nчасть' or 'слово -\n часть' -> 'словочасть'
                    s = re.sub(r'([A-Za-zА-Яа-яЁё0-9])\s*[-]\s*[\r\n]+\s*([A-Za-zА-Яа-яЁё0-9])', r'\1\2', s)

                    # Replace tabs and remaining line breaks with a single space
                    s = s.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')

                    # Collapse multiple whitespace to single space and strip
                    s = ' '.join(s.split())

                    # Conservative intra-word glue: remove single spaces between long
                    # letter/digit sequences only when both sides are reasonably long.
                    # Use word characters (unicode) via \w with re.UNICODE.
                    try:
                        s = re.sub(r'(?<=\b\w{4})\s+(?=\w{3}\b)', '', s, flags=re.U)
                    except re.error:
                        # Fallback: if unicode flags not accepted, do simpler collapse
                        s = re.sub(r'(?<=\w{4})\s+(?=\w{3})', '', s)

                    return s

                text = normalize_text(doc.get('text', '') or '')
                title = normalize_text(doc.get('title', '') or '')
                
                text_bytes = len(text.encode('utf-8'))
                total_text_bytes += text_bytes
                
                # Запись — пропускаем повторы по id
                doc_id = doc.get('id', '')
                total_input_docs += 1
                if not doc_id:
                    # Если нет id — просто пропускаем запись и логируем
                    dup_log.write(f"MISSING_ID in input file at doc #{total_input_docs}\n")
                    continue
                if doc_id in seen_ids:
                    # логируем файл/заголовок и пропускаем
                    dup_log.write(f"DUPLICATE\t{doc_id}\t{title}\n")
                    continue
                # уникальный документ — записываем (title and text are already cleaned)
                seen_ids.add(doc_id)
                current_file.write(f"{doc_id}\t{title}\t{text}\n")
                written_docs += 1
                
                # Прогресс
                if total_input_docs % 5000 == 0:
                    print(f"  ... seen {total_input_docs}, written {written_docs}")
        
        # Закрываем последний файл
        if current_file:
            current_file.close()
        dup_log.close()
            
    except Exception as e:
        print(f"Ошибка при обработке: {e}")
        return
    
    # Рассчитываем статистику
    avg_doc_size = total_text_bytes / written_docs if written_docs > 0 else 0
    
    # Сохраняем info.txt
    with open(f"{output_dir}/info.txt", 'w', encoding='utf-8') as f:
        f.write("СТАТИСТИКА КОРПУСА\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Всего документов (входных строк): {total_input_docs}\n")
        f.write(f"Всего уникальных документов: {written_docs}\n")
        f.write(f"Размер сырых данных: {total_raw_bytes:,} байт\n")
        f.write(f"Размер текста (после очистки): {total_text_bytes:,} байт\n")
        f.write(f"Средний размер документа: {avg_doc_size:.0f} байт\n")
        f.write(f"Файлов в корпусе: {file_count}\n")
        f.write(f"Документов в файле (максимум): {docs_per_file}\n")
        f.write(f"Источник: Википедия (категория Кинематограф)\n")
        f.write(f"Формат: TSV (id\\ttitle\\ttext)\n")
        f.write(f"Кодировка: UTF-8\n")
    
    # Результат
    print(f"\nГотово")
    print(f"Входных документов: {total_input_docs}")
    print(f"Уникальных документов записано: {written_docs}")
    print(f"Создано файлов: {file_count}")
    print(f"Результат сохранен в: {os.path.abspath(output_dir)}")
    
    # Показываем пример
    if os.path.exists(f"{output_dir}/part_001.tsv"):
        print(f"\nПример первого документа:")
        with open(f"{output_dir}/part_001.tsv", 'r', encoding='utf-8') as f:
            # Пропускаем заголовок
            f.readline()
            first_line = f.readline()
            if first_line:
                parts = first_line.strip().split('\t')
                if len(parts) >= 3:
                    print(f"  ID: {parts[0]}")
                    print(f"  Заголовок: {parts[1]}")
                    print(f"  Текст (начало): {parts[2][:80]}...")

if __name__ == "__main__":
    main()