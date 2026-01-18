# такое задание можно безошибочно навайбкодить за 2-3 запроса в какой-нибудь copilot или chatgpt :о
# оставлю часть комментариев формальными как "для себя" потому что всё равно считаю, что код пройдёт через ИИ-агента в первую очередь
# пеп-8 говорит что комментарии должны быть для всего кода, но чистый код говорит, что код должен быть самопрезентуемым 
import argparse
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

class HTTPRequest:
    def __init__(self, timeout=10.0):
        self.timeout = timeout
        self.lock = threading.Lock()
    
    def check_url(self, url):
        # Простая проверка URL, http проверять не будем потому что они без s(секуре) :o
        if not url.startswith(('https://')):
            return False
        # несмотря на то, что это startswith уже делает это, но всё равно надо проверить на всякий случай
        parts = url.split('://')
        if len(parts) != 2:
            return False
        if not parts[1].strip():  # Если после :// пусто
            return False
        return True
    
    # соберём всю информацию о запросе и посчитаем скорость пинг-понга
    def make_request(self, url):
        start_time = time.time()
        try:
            response = requests.get(url, timeout=self.timeout)
            elapsed = time.time() - start_time
            
            if response.status_code < 400:
                return True, elapsed, response.status_code
            else:
                return False, elapsed, response.status_code
                
        except requests.exceptions.Timeout:
            return False, self.timeout, None
        except requests.exceptions.ConnectionError:
            elapsed = time.time() - start_time
            return False, elapsed, None
        except Exception:
            elapsed = time.time() - start_time
            return False, elapsed, None
    
    def test_one_host(self, url, count):
        results = {
            'host': url,
            'success': 0,
            'failed': 0,
            'errors': 0,
            'times': []
        }
        
        for i in range(count):
            success, elapsed, status_code = self.make_request(url)
            
            # залочим поток, потому что это смысл корутин в asyncio
            with self.lock:
                if success:
                    results['success'] += 1
                    results['times'].append(elapsed)
                elif status_code and 400 <= status_code < 600:
                    results['failed'] += 1
                    results['times'].append(elapsed)
                else:
                    results['errors'] += 1
        
        # считаем статистику на вывод в документик
        if results['times']:
            results['min_time'] = min(results['times'])
            results['max_time'] = max(results['times'])
            results['avg_time'] = sum(results['times']) / len(results['times'])
        else:
            results['min_time'] = results['max_time'] = results['avg_time'] = 0
        
        return results
    
    # выведу в отдельную функцию просто чтобы показать что могу
    def test_hosts_one_by_one(self, urls, count):
        all_results = []
        for url in urls:
            result = self.test_one_host(url, count)
            all_results.append(result)
        return all_results
    
    def test_hosts_at_same_time(self, urls, count, workers=5):
        all_results = []
        
        # первый раз использую эту либу по этому сделаю как предложит copilot хых
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # создаем задачи для каждого URL
            futures = {}
            for url in urls:
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


def main():
    parser = argparse.ArgumentParser(description='Прога для тестирования доступности сервера')
    
    # fixme: в argparse лежит дефолтный help на английском, ваще без понятия как фиксить без костылей 
    # костыль должен быть в таком виде: 
    #parser.add_help(False) #???
    #parser.add_argument(..."--help",...)
    
    parser.add_argument('-H', '--hosts', help='Адреса для тестирования через запятую')
    parser.add_argument('-C', '--count', type=int, default=1, help='Количество запросов на каждый хост')
    parser.add_argument('-F', '--file', help='Файл со списком адресов (каждый с новой строки)')
    parser.add_argument('-O', '--output', help='Файл для сохранения результатов')
    parser.add_argument('--concurrent', action='store_true', help='Использовать параллельные запросы')
    parser.add_argument('--workers', type=int, default=5, help='Количество потоков для параллельных запросов')
    parser.add_argument('--timeout', type=float, default=10.0, help='Таймаут запроса в секундах')
    
    args = parser.parse_args()
    
    # проверим способ задания адресов
    if not args.hosts and not args.file:
        print("Ошибка: нужно указать адреса через --hosts или --file")
        parser.print_help()
        # поскольку по заданию приложение должно быть консольным, то просто прекращаем программу если не удалось пройти проверку
        sys.exit(1)
    
    # проверим что не указаны оба способа одновременно
    if args.hosts and args.file:
        print("Ошибка: можно использовать только --hosts или --file, но не оба сразу")
        parser.print_help()
        # ну и по логике первой проверки просто убьём 
        sys.exit(1)
    
    # запросов не должно быть меньше нуля 
    if args.count <= 0:
        print("Ошибка: количество запросов должно быть больше 0")
        sys.exit(1)

    # так называемая "проверка на дурака" который наверняка захочет сломать прогу
    dangerous_chars = [';', '|', '&', '`', '$', '(', ')', '{', '}', '[', ']', '<', '>', '!']
    
    if args.hosts:
        # проверяем хосты на опасные символы
        for host in args.hosts.split(','):
            host = host.strip()
            for char in dangerous_chars:
                if char in host:
                    print(f"Ошибка: обнаружен некорректный символ '{char}' в хосте: {host}")
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
        # Разделяем строку по запятым
        urls = args.hosts.split(',')
        # Убираем лишние пробелы
        urls = [url.strip() for url in urls]
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:  # Пропускаем пустые строки
                        urls.append(line)
        except Exception as e:
            print(f"Ошибка при чтении файла: {e}")
            sys.exit(1)
    
    # проверяем что есть хоть какие-то адреса
    if not urls:
        print("Ошибка: не указано ни одного адреса для тестирования")
        sys.exit(1)
    
    # создаем объект для тестирования
    benchmark = HTTPRequest(timeout=args.timeout)
    
    # создадим списки чтобы засунуть в них адреса 
    good_urls = []
    bad_urls = []
    
    for url in urls:
        if benchmark.check_url(url):
            good_urls.append(url)
        else:
            bad_urls.append(url)
    
    # про плохие адреса сообщим
    if bad_urls:
        print("Предупреждение: следующие адреса пропущены из-за некорректного формата:")
        for url in bad_urls:
            print(f"  - {url}")
        print()
    
    # если ваще все плохие прям сильно сообщим 
    if not good_urls:
        print("Ошибка: все адреса имеют некорректный формат")
        print("Формат должен быть: http://example.com или https://example.com")
        sys.exit(1)
    
    try:
        print(f"Начинаю проверку {len(good_urls)} хостов...")
        print(f"Запросов на каждый хост: {args.count}")
        
        start_time = time.time()
        
        if args.concurrent:
            print(f"Использую параллельные запросы ({args.workers} потоков)")
            results = benchmark.test_hosts_at_same_time(good_urls, args.count, args.workers)
        else:
            print("Использую последовательные запросы")
            results = benchmark.test_hosts_one_by_one(good_urls, args.count)
        
        total_time = time.time() - start_time
        
        # Показываем результаты
        show_results(results, args.output)
        
        print(f"\nОбщее время проверки: {total_time:.2f} секунд")
        
    except KeyboardInterrupt:
        print("\n\nПроверка прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()