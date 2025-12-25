#!/usr/bin/env python3
import json
import os
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
    
    # Статистика
    total_docs = 0
    total_raw_bytes = 0
    total_text_bytes = 0
    file_count = 0
    current_file = None
    
    print(f"Читаю {input_file}")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                
                total_raw_bytes += len(line.encode('utf-8'))
                doc = json.loads(line)
                
                # Новый файл
                if total_docs % docs_per_file == 0:
                    if current_file:
                        current_file.close()
                    
                    file_count += 1
                    filename = f"{output_dir}/part_{file_count:03d}.tsv"
                    current_file = open(filename, 'w', encoding='utf-8')
                    current_file.write("id\ttitle\ttext\n")
                
                # Текст
                text = doc.get('text', '')
                # Убираем табы и переносы, сокращаем множественные пробелы
                text_clean = ' '.join(text.replace('\t', ' ')
                                           .replace('\n', ' ')
                                           .replace('\r', ' ')
                                           .split())
                
                text_bytes = len(text_clean.encode('utf-8'))
                total_text_bytes += text_bytes
                
                # Запись
                doc_id = doc.get('id', '')
                title = doc.get('title', '').replace('\t', ' ')
                current_file.write(f"{doc_id}\t{title}\t{text_clean}\n")
                total_docs += 1
                
                # Прогресс
                if total_docs % 5000 == 0:
                    print(f"  ... {total_docs}")
        
        # Закрываем последний файл
        if current_file:
            current_file.close()
            
    except Exception as e:
        print(f"Ошибка при обработке: {e}")
        return
    
    # Рассчитываем статистику
    avg_doc_size = total_text_bytes / total_docs if total_docs > 0 else 0
    
    # Сохраняем info.txt
    with open(f"{output_dir}/info.txt", 'w', encoding='utf-8') as f:
        f.write("СТАТИСТИКА КОРПУСА\n")
        f.write("=" * 40 + "\n\n")
        f.write(f"Всего документов: {total_docs}\n")
        f.write(f"Размер сырых данных: {total_raw_bytes:,} байт\n")
        f.write(f"Размер текста (после очистки): {total_text_bytes:,} байт\n")
        f.write(f"Средний размер документа: {avg_doc_size:.0f} байт\n")
        f.write(f"Файлов в корпусе: {file_count}\n")
        f.write(f"Документов в файле: {docs_per_file}\n")
        f.write(f"Источник: Википедия (категория Кинематограф)\n")
        f.write(f"Формат: TSV (id\\ttitle\\ttext)\n")
        f.write(f"Кодировка: UTF-8\n")
    
    # Результат
    print(f"\nГотово")
    print(f"Обработано документов: {total_docs}")
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