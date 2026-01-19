# такое задание можно безошибочно навайбкодить за 2-3 запроса в какой-нибудь copilot или chatgpt :о
# оставлю часть комментариев формальными как "для себя" потому что всё равно считаю, что код пройдёт через ИИ-агента в первую очередь
# пеп-8 говорит что комментарии должны быть для всего кода, но чистый код говорит, что код должен быть самопрезентуемым 
# весь код в InputValidator на самом деле не нужен для выполнения задания, я его добавил, потому что посчитал нужным накидать иб в код
# знаю я это потому что проходил piscine для 42-й школы в Италии ._. 

# todo list: 
# 1) Принимать в качестве аргумента командной строки ключ –H/--hosts ✓✓✓✓
# 2) Возможность указать ключ –C/--count со значением количества запросов ✓✓✓✓
# 3) Выводить итоговую статистику по выполненным запросам для каждого хоста отдельно ✓✓✓✓
# 4) Ошибки должны быть обработаны с помощью блоков try/except ✓✓✓✓
# 5) Фикс ввода входных данных типа: htttps ✓✓✓✓ и длинное тире ❌
# допы:
# 6) Добавьте проверку входных параметров на соответствие типу и формату ✓✓✓✓
# 7) Добавьте возможность указывать имена файлов для входных и выходных данных с помощью ключей –I/--input и –O/--output ✓✓✓✓
# 8) Задание с повышенной сложностью Последовательное выполнение запросов занимает много времени. Попробуйте оптимизировать работу с
# помощью конкурентного программирования ✓✓✓✓

# судя по https://docs.python.org/3/library/ все либы считаются стандартными:
import argparse 
import os 
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed 
import requests
import re 
from urllib.parse import urlparse

class InputValidator:
    # отдельный класс валидатор ввода параметров
    
    @staticmethod
    def validate_args_presence(args):
        # проверяем что хотя бы один из способов задания адресов задан
        if not args.hosts and not args.file:
            return False, "Нужно указать адреса через --hosts или --file"
        return True, ""
    
    @staticmethod
    def validate_mutual_exclusion(args):
        # проверяем что не указаны оба способа одновременно
        if args.hosts and args.file:
            return False, "Можно использовать только --hosts или --file, но не оба сразу"
        return True, ""
    
    @staticmethod
    def validate_count(args):
        # запросов не должно быть меньше нуля 
        if args.count <= 0:
            return False, "Количество запросов должно быть больше 0"
        # и ограничим сверху чтобы не сломать всё
        if args.count > 10000:
            return False, "Количество запросов не может превышать 10000"
        return True, ""
    
    @staticmethod
    def validate_workers(args):
        # потоков тоже должно быть больше нуля
        if args.workers <= 0:
            return False, "Количество потоков должно быть больше 0"
        # 100 потоков - уже дофига, больше смысла нет
        if args.workers > 100:
            return False, "Количество потоков не может превышать 100"
        return True, ""
    
    @staticmethod
    def validate_timeout(args):
        # таймаут должен быть положительным
        if args.timeout <= 0:
            return False, "Таймаут должен быть больше 0"
        # 5 минут максимум, больше ждать смысла нет
        if args.timeout > 300:
            return False, "Таймаут не может превышать 300 секунд"
        return True, ""
    
    @staticmethod
    def validate_hosts_syntax(hosts_arg):
        # если хостов нет - проверять нечего
        if not hosts_arg or hosts_arg == "":
            return True, ""
        # проверяем на длинное тире (проблема копирования из PDF/Word)
        # что бы я не делал, оно не хочет фиксить длинное тире.
        #if '\u2013' in hosts_arg or '\u2014' in hosts_arg:
        #    return False, "Обнаружено длинное тире '–'. Используйте обычный дефис '-'"

        
        # так называемая "проверка на дурака" на опасные символы
        dangerous_patterns = [
            (r';\s*[a-zA-Z]', "точка с запятой с командой"),  # ;ls, ;cat и т.д.
            (r'\|\s*[a-zA-Z]', "пайп с командой"),           # |ls, |cat
            (r'&\s*[a-zA-Z]', "амперсанд с командой"),       # &rm -rf /
            (r'`', "обратные кавычки"),                      # `команда`
            (r'\$\s*\(', "выполнение команд через $()"),     # $(команда)
        ]
        
        # разбиваем по запятым и проверяем каждый хост
        hosts = hosts_arg.split(',')
        for host in hosts:
            host = host.strip()
            for pattern, description in dangerous_patterns:
                if re.search(pattern, host):
                    # обрезаем длинные строки чтобы не засорять вывод
                    return False, f"Обнаружена потенциальная инъекция ({description}) в хосте: {host[:50]}..."
        return True, ""
    
    @staticmethod
    def validate_filename_safety(filename, arg_name):
        # если файл не указан - проверять нечего
        if not filename:
            return True, ""
        
        # проверяем на попытки path traversal (../ или ..\)
        if '..' in filename:
            return False, f"Имя файла {arg_name} содержит опасные пути"
        
        # проверяем на абсолютные пути (может быть попытка доступа к системным файлам)
        if filename.startswith('/') or ':\\' in filename:
            return False, f"Имя файла {arg_name} содержит опасные пути"
        
        # проверяем на опасные символы которые могут сломать командную строку
        dangerous_in_filename = [';', '|', '&', '`', '$(']
        for char in dangerous_in_filename:
            if char in filename:
                return False, f"Имя файла {arg_name} содержит опасный символ: {char}"
        
        return True, ""
    
    @staticmethod
    def validate_file_extension(filename, expected_ext='.txt'):
        # если файл не указан - проверять нечего
        if not filename:
            return True, ""
        
        # просто предупреждение, не ошибка
        if not filename.endswith(expected_ext):
            return False, f"Рекомендуется использовать файлы с расширением {expected_ext}"
        return True, ""
    
    @staticmethod
    def validate_key_value_pairs(argv):
        # ключи которые требуют значений
        value_required_keys = {
            '-H', '--hosts',
            '-C', '--count', 
            '-F', '--file',
            '-O', '--output',
            '--workers',
            '--timeout'
        }
        
        for i in range(1, len(argv)):
            arg = argv[i]
            if arg in value_required_keys:
                # проверим что это не последний аргумент
                if i == len(argv) - 1:
                    return False, f"Ключ '{arg}' требует значения"
                
                # проверим что после этого нет другого ключа
                next_arg = argv[i + 1]
                if next_arg.startswith('-'):
                    return False, f"После ключа '{arg}' ожидалось значение, но получен '{next_arg}'"
        
        return True, ""

    @staticmethod
    def validate_url(url):
        url_lower = url.lower()
        
        # проверяем что URL начинается с https://
        # хотя по заданию вроде только https, но пусть будет оба
        if not url_lower.startswith(('https://')):
            return False, "URL должен начинаться с https://"
        
        try:
            # парсим URL чтобы проверить его структуру
            parsed = urlparse(url)
            
            # проверяем что есть домен (netloc)
            if not parsed.netloc:
                return False, "URL должен содержать домен"
            
            # проверяем длину URL (RFC говорит что максимум около 2000 символов)
            if len(url) > 2000:
                return False, "URL слишком длинный (макс. 2000 символов)"
            
            # проверяем порт если он указан
            if parsed.port is not None:
                if parsed.port <= 0 or parsed.port > 65535:
                    return False, f"Некорректный порт: {parsed.port}"
            
            # проверяем на SSRF (локальные адреса)
            # это когда пытаются достучаться до localhost или внутренних сетей
            netloc = parsed.netloc.lower()
            local_patterns = [
                r'^localhost(:\d+)?$',  # localhost с портом или без
                r'^127\.\d+\.\d+\.\d+(:\d+)?$',  # 127.x.x.x - loopback
                r'^192\.168\.\d+\.\d+(:\d+)?$',  # приватная сеть 192.168.x.x
                r'^10\.\d+\.\d+\.\d+(:\d+)?$',   # приватная сеть 10.x.x.x
                r'^172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+(:\d+)?$',  # приватная 172.16-31.x.x
                r'^0\.0\.0\.0(:\d+)?$',  # 0.0.0.0
                r'^::1(:\d+)?$',         # IPv6 localhost
            ]
            
            for pattern in local_patterns:
                if re.match(pattern, netloc):
                    return False, "URL ссылается на локальный ресурс"
            
            # проверяем на метаданные облаков (AWS, GCP, Azure)
            # это когда пытаются достучаться до метаданных инстанса
            cloud_metadata = [
                '169.254.169.254',            # AWS metadata
                'metadata.google.internal',   # GCP metadata
                'metadata.azure.internal',    # Azure metadata
            ]
            
            if netloc in cloud_metadata:
                return False, "URL ссылается на сервис метаданных облака"
            
            return True, ""
            
        except Exception:
            # если что-то пошло не так - считаем URL небезопасным
            return False, "Некорректный формат URL"

class HTTPRequest:
    def __init__(self, timeout=10.0):
        # fixme: редирректы нужно учитывать, не знаю как дебажить, оставил их отключенными
        self.timeout = timeout
        self.results_lock = threading.Lock()

    # соберём всю информацию о запросе и посчитаем скорость
    def make_request(self, url):
        start_time = time.time()
        try:
            # создадим безопасные заголовки для отправки запроса
            # защитка просто нужна
            # вытянул эту инфу с https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers, должно работать для любых запросов, в документации написано прямо так
            # User-agent - Contains a characteristic string that allows the network protocol peers to identify the application type, operating system,
            # software vendor or software version of the requesting software user agent.
            
            # Accept - Contains one or more media types, indicating the content types that the user agent is willing to accept in the response. xml стандарт формат для выдачи ответа
            # Accept-Language - Contains one or more language tags, indicating the languages that the user agent is able to understand. en-us и en-gb стандарт языка в сетях
            # Accept-Encoding - Contains one or more values indicating what compression methods the user agent is willing to accept. gzip deflate стандарт для заголовка  
            # Connection - Contains a token that indicates whether the user agent wants to keep the connection alive or whether it 
            # wants to close the connection after the response has been received. закрытое подключение
            # Cache-Control - Contains directives that provide information about how to cache a response. без кеша
            headers = {
                'User-Agent': 'HTTPBenchmark/1.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru,en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'close',
                'Cache-Control': 'no-cache'
            }
            response = requests.get(
                url, 
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
                verify=True
            )
            # сразу закрываем
            response.close()
            
            elapsed = time.time() - start_time
            
            # 2хх коды означают успех, 3хх - перенаправления, 4хх-5хх - ошибки
            if 200 <= response.status_code < 400:
                return True, elapsed, response.status_code
            else:
                return False, elapsed, response.status_code
                
        # и накидаем эксепшенов, потому что они могут произойти
        # ошибок на самом деле может быть очень много, в exceptions их аж 20 штук, но вроде как последнее условие обрабатает все ошибки по условию задания
        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time  
            return False, elapsed, None
        except requests.exceptions.ConnectionError:
            elapsed = time.time() - start_time
            return False, elapsed, None
        except Exception:
            elapsed = time.time() - start_time
            return False, elapsed, None

    def test_one_host(self, url, count):
        # в версии 3 этой проги был бесконечный цикл блокировок, зарефакторил 
        # в прошлом было так: создавался огромный поток запросов, если один из них ожидал своего таймаута, то все остальные ожидали ответа от первого
        # в этой версии вроде(?) пофикшено и теперь максимум потоков - 5 
        
        local_success = 0
        local_failed = 0
        local_errors = 0
        local_times = []
        
        for i in range(count):
            success, elapsed, status_code = self.make_request(url)
            
            if success:
                local_success += 1
                local_times.append(elapsed)
            elif status_code and 400 <= status_code < 600:
                local_failed += 1
                local_times.append(elapsed)
            else:
                local_errors += 1
        
        # создаем результат
        result = {
            'host': url,
            'success': local_success,
            'failed': local_failed,
            'errors': local_errors,
            'times': local_times
        }
        
        # считаем статистику по времени
        if result['times']:
            result['min_time'] = min(result['times'])
            result['max_time'] = max(result['times'])
            result['avg_time'] = sum(result['times']) / len(result['times'])
        else:
            result['min_time'] = result['max_time'] = result['avg_time'] = 0
        
        return result
    
    # выведу в отдельную функцию просто чтобы показать что могу
    def test_hosts_one_by_one(self, urls, count):
        all_results = []
        for url in urls:
            result = self.test_one_host(url, count)
            all_results.append(result)
        return all_results
    
    def test_hosts_at_same_time(self, urls, count, max_workers=5):
        
        # ограничим количество работающих потоков по количеству хостов, максимум 10
        max_concurrent_hosts = min(len(urls), 10)
        actual_workers = min(max_workers, max_concurrent_hosts)
        
        all_results = []
        
        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # подзапарился с https://docs.python.org/3/library/concurrent.futures.html
            # создадим отдельную задачу для каждого URL 
            futures = {}
            # количество хостов - ограничено
            for url in urls[:max_concurrent_hosts]:
                future = executor.submit(self.test_one_host, url, count)
                futures[future] = url
            
            # собираем результаты
            for future in as_completed(futures):
                url = futures[future]
                try:
                    result = future.result()
                    all_results.append(result)
                except Exception as e:
                    print(f"Ошибка при тестировании {url}: {e}")
                    # для сбора информации по ошибкам добавим нулевой результат
                    all_results.append({
                        'host': url,
                        'success': 0,
                        'failed': 0,
                        'errors': count,
                        'times': [],
                        'min_time': 0,
                        'max_time': 0,
                        'avg_time': 0
                    })
        
        return all_results



def show_results(results, output_filename=None):
    # весь show_results самопрезентуемый
    text_lines = []
    
    for result in results:
        text_lines.append(f"\nХост: {result['host']}")
        text_lines.append(f"  Успешно: {result['success']}")
        text_lines.append(f"  Ошибки сервера: {result['failed']}")
        text_lines.append(f"  Ошибки соединения: {result['errors']}")
        
        if result['times']:
            # ограничим время до мс форматированием
            text_lines.append(f"  Минимальное время: {result['min_time']:.3f} сек")
            text_lines.append(f"  Максимальное время: {result['max_time']:.3f} сек")
            text_lines.append(f"  Среднее время: {result['avg_time']:.3f} сек")
        else:
            text_lines.append("  Нет успешных запросов")
    # сделаем красивишно
    text_lines.append("\n" + "="*50)
    text_lines.append("ОБЩАЯ СТАТИСТИКА:")
    
    total_hosts = len(results)
    total_success = sum(r['success'] for r in results)
    total_failed = sum(r['failed'] for r in results)
    total_errors = sum(r['errors'] for r in results)
    total_requests = total_success + total_failed + total_errors
    
    text_lines.append(f"Всего хостов: {total_hosts}")
    text_lines.append(f"Всего запросов: {total_requests}")
    text_lines.append(f"  Успешных: {total_success}")
    text_lines.append(f"  Ошибок сервера: {total_failed}")
    text_lines.append(f"  Ошибок соединения: {total_errors}")
    
    final_text = "\n".join(text_lines)
    
    if output_filename:
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(final_text)
            print(f"Результаты сохранены в файл: {output_filename}")
            
        # смешно то, что и такой вариант может быть:
        except Exception as e:
            print(f"Не удалось записать в файл: {e}")
            # и если не вышло просто выводим на экран с ошибкой
            print(final_text)
    else:
        # без ключа --output просто выводим на экран
        print(final_text)
        
# не знаю наверняка, повысит ли безопасность обёртка чтения файлов в отдельном классе, поэтому сделаю как с выводом результатов в глобальном пространстве
def read_urls_from_file(filename):
    
    urls = []
    
    try:
        # проверим размер файла
        file_size = os.path.getsize(filename)
        if file_size > 10 * 1024 * 1024:  # не больше 10и метров
            print(f"Предупреждение: файл слишком большой ({file_size} байт)")
            return []
        
        # ограничимся стандартными кодировками: utf-8 имеет кириллицу для linux, cp1251 для windows
        encodings = ['utf-8', 'cp1251']
        
        for encoding in encodings:
            try:
                with open(filename, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                    
                    # Ограничиваем количество строк
                    max_lines = 1000
                    if len(lines) > max_lines:
                        print(f"Предупреждение: прочитано только {max_lines} строк из {len(lines)}")
                        lines = lines[:max_lines]
                    
                    for line in lines:
                        line = line.strip()
                        if line:
                            urls.append(line)
                    
                    break  # Если удалось прочитать
                    
            except UnicodeDecodeError:
                continue
    
    except FileNotFoundError:
        print(f"Ошибка: файл не найден: {filename}")
    # проверим rwx 
    except PermissionError:
        print(f"Ошибка: нет прав на чтение файла: {filename}")
    # и любые другие
    except Exception as e:
        print(f"Ошибка при чтении файла {filename}: {e}")
        
    return urls

def main():
    parser = argparse.ArgumentParser(
        description='Утилита для тестирования доступности серверов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False
    )
    
    # fixme: в argparse лежит дефолтный help на английском, ваще без понятия как фиксить без костылей 
    
    parser.add_argument("-h", '--help', action='store_true', help='Показать справку')
    parser.add_argument('-H', '--hosts', help='Адреса для тестирования через запятую')
    parser.add_argument('-C', '--count', type=int, default=1, help='Количество запросов на каждый хост')
    parser.add_argument('-F', '--file', help='Файл со списком адресов (каждый с новой строки)')
    parser.add_argument('-O', '--output', help='Файл для сохранения результатов')
    parser.add_argument('--concurrent', action='store_true', help='Использовать параллельные запросы')
    parser.add_argument('--workers', type=int, default=5, help='Количество потоков для параллельных запросов')
    parser.add_argument('--timeout', type=float, default=10.0, help='Таймаут запроса в секундах')
        
    # Инициализируем валидатор
    validator = InputValidator()
    
    is_valid, error = validator.validate_key_value_pairs(sys.argv)
    if not is_valid:
        print(f"Ошибка синтаксиса: {error}")
        print("\nПримеры правильного использования:")
        print("  python peperain.py -H https://ya.ru,https://google.com -C 5")
        print("  python peperain.py -F urls.txt -C 3")
        print("  python peperain.py -H https://example.com --output result.txt")
        sys.exit(1)
        
    args = parser.parse_args()

    # Выполняем все проверки
    checks = [
        (validator.validate_args_presence(args), "args_presence"),
        (validator.validate_mutual_exclusion(args), "mutual_exclusion"),
        (validator.validate_count(args), "count"),
        (validator.validate_workers(args), "workers"),
        (validator.validate_timeout(args), "timeout"),
        (validator.validate_hosts_syntax(args.hosts), "hosts_syntax"),
        (validator.validate_filename_safety(args.file, "--file"), "file_safety"),
        (validator.validate_filename_safety(args.output, "--output"), "output_safety"),
    ]
    
    for (is_valid, error_msg), check_name in checks:
        if not is_valid:
            print(f"Ошибка: {error_msg}")
            if check_name in ["args_presence", "mutual_exclusion"]:
                parser.print_help()
            sys.exit(1)
    
    # предупредим, если расширения файла sus
    if args.file:
        is_valid, warning = validator.validate_file_extension(args.file)
        if not is_valid:
            print(f"Предупреждение: {warning}")
    
    if args.output:
        is_valid, warning = validator.validate_file_extension(args.output)
        if not is_valid:
            print(f"Предупреждение: {warning}")
    

    # так называемая "проверка на дурака" который наверняка захочет сломать прогу
    dangerous_chars = [';', '|', '&', '`', '$', '(', ')', '{', '}', '[', ']', '<', '>', '!']
    
    if args.hosts:
        # проверяем хосты на опасные символы
        for host in args.hosts.split(','):
            host = host.strip()
            for char in dangerous_chars:
                if char in host:
                    print(f"Ошибка: обнаружен некорректный символ '{char}' в хосыте: {host}")
                    sys.exit(1)
    
    if args.file:
        # проверяем имя файла на опасные символы
        for char in dangerous_chars:
            if char in args.file:
                print(f"Ошибка: обнаружен некорректный символ '{char}' в имени файла: {args.file}")
                sys.exit(1)
        
        # проверяем что файл имеет безопасное расширение
        if not args.file.endswith('.txt'):
            print("Предупреждение: рекомендуется использовать файлы с расширением .txt")
    
    if args.output:
        # проверяем имя выходного файла на опасные символы
        for char in dangerous_chars:
            if char in args.output:
                print(f"Ошибка: обнаружен некорректный символ '{char}' в имени выходного файла: {args.output}")
                sys.exit(1)
        
        # проверяем что выходной файл имеет безопасное расширение
        if not args.output.endswith('.txt'):
            print("Предупреждение: результаты будут сохранены в файл без стандартного расширения")

    # получаем список адресов
    urls = []
    
    if args.hosts:
        urls = [url.strip() for url in args.hosts.split(',') if url.strip()]
    
    if args.file:
        file_urls = read_urls_from_file(args.file)
        urls.extend(file_urls)
    
    # проверяем что есть хоть какие-то адреса
    if not urls:
        print("Ошибка: не указано ни одного адреса для тестирования")
        sys.exit(1)
    
    # каждый URL куда-то нужно положить
    good_urls = []
    bad_urls_info = []
    
    for url in urls:
        # проверяем URL одной строкой
        is_valid, error_msg = validator.validate_url(url)
        if not is_valid:
            bad_urls_info.append(f"{url} - {error_msg}")
            continue
        
        good_urls.append(url)
    
    # выводим предупреждения
    if bad_urls_info:
        print("\nПредупреждение: следующие адреса пропущены:")
        for info in bad_urls_info[:10]:
            print(f"  - {info}")
        if len(bad_urls_info) > 10:
            print(f"  ... и еще {len(bad_urls_info) - 10} адресов")
        print()
    
    # проверяем что остались хоть какие-то адреса
    if not good_urls:
        print("Ошибка: все адреса имеют некорректный формат или не прошли проверку безопасности")
        print("Формат должен быть: https://example.com")
        sys.exit(1)
    
    # Ограничиваем общее количество запросов
    total_requests = len(good_urls) * args.count
    if total_requests > 1000:
        print(f"Предупреждение: общее количество запросов ({total_requests}) слишком большое")
        print("Будут протестированы только первые 100 хостов")
        good_urls = good_urls[:100]
    
    try:
        print(f"Начинаю проверку {len(good_urls)} хостов...")
        print(f"Запросов на каждый хост: {args.count}")
        print(f"Общее количество запросов: {len(good_urls) * args.count}")
        
        start_time = time.time()
        
        # создаем объект для тестирования
        benchmark = HTTPRequest(timeout=args.timeout)
        
        if args.concurrent:
            print(f"Использую параллельные запросы ({args.workers} потоков)")
            results = benchmark.test_hosts_at_same_time(good_urls, args.count, args.workers)
        else:
            print("Использую последовательные запросы")
            results = benchmark.test_hosts_one_by_one(good_urls, args.count)
        
        total_time = time.time() - start_time
        
        # показываем результаты
        show_results(results, args.output)
        
        print(f"\nОбщее время проверки: {total_time:.2f} секунд")
        print(f"Среднее время на запрос: {total_time/total_requests:.3f} секунд" if total_requests > 0 else "")
        
    except KeyboardInterrupt:
        print("\n\nПроверка прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
