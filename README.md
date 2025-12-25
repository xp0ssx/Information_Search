# Лабораторные работы  
## по курсу «Информационный поиск»

**Студент:** Кудинов Денис Викторович 
**Группа:** М8О-412Б-22  
Лабораторные работы по информационному поиску (тематика — кинематограф).

1) Распаковать архив (если есть):

```bash
# tar.gz
tar -xzf Information_Search.tar.gz
cd Information_Search
```

2) Создать виртуальное окружение и установить зависимости:

```bash
python3 -m venv myenv
./myenv/bin/pip install --upgrade pip
./myenv/bin/pip install -r requirements.txt
```

3) Быстрый тест (sample):

```bash
./myenv/bin/python3 corpus_analyze/tokenize.py --sample 200 --outdir corpus_analyze --corpus corpus
./myenv/bin/python3 indexer/build_index.py --sample 1000 --outdir indexes --corpus corpus --force
./myenv/bin/python3 webapp/app.py --index indexes/raw --host 127.0.0.1 --port 8080
```

4) Полная сборка (внимание: долго и займёт место):

```bash
make venv    # создаст ./myenv, если его нет
make install # установит зависимости
make tokenize
make index
make serve   # запустит веб‑интерфейс
```

5) Тесты:

```bash
make test
```
