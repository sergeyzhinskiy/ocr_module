import re
from typing import Dict
from .file_processing import extract_text

def classify_document(text: str) -> str:
    t = text.lower()
    
    # Затем проверяем обычные чеки и счета
    if any(w in t for w in ["чек", "касс", "итог", "сдача", "оплата", "приходный ордер", "квитанция", "перевод", "оплачено", "исполнено", ""]):
        return "receipt"
    if any(w in t for w in ["счет", "счёт", "накладная", "invoice", "счет-фактура", "р/с", "квитанция"]):
        return "invoice"

    # Ключевые слова для PayPal
    paypal_keywords = ["paypal", "ppl", "pay pal", "пейпал", "пайпал"]
    
    # Сначала проверяем PayPal - это наш приоритет для иностранных платежей
    if any(w in t for w in paypal_keywords):
        return "paypal_receipt"
    
    
    
    return "unknown"

def extract_fields(text: str) -> Dict[str, str]:
    fields = {}
    text_lower = text.lower()
    
    # Определяем тип документа
    doc_type = classify_document(text)
    
    # Для PayPal-документов используем специальную логику
    if doc_type == "paypal_receipt":
        return extract_paypal_fields(text)
    
    # Для российских документов используем общую логику
    # дата
    date_patterns = [
        r"(\d{2}[./-]\d{2}[./-]\d{2,4})",  # DD.MM.YYYY
        r"(\d{4}[./-]\d{2}[./-]\d{2})",    # YYYY-MM-DD
        r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})",  # 12 января 2023
    ]
    
    for pattern in date_patterns:
        m = re.search(pattern, text_lower)
        if m: 
            fields["date"] = m.group(1)
            break
    
    # сумма
    m = re.search(r"(?:итог|сумма|к оплате|total)\s*[:=]?\s*([0-9\s]+[.,][0-9]{2})", text_lower)
    if m: 
        fields["total"] = m.group(1)
    
    # номер
    m = re.search(r"(?:№|номер)\s*[:=]?\s*([A-Za-zА-Яа-я0-9\-_/]+)", text)
    if m: 
        fields["number"] = m.group(1)
    
    return fields

def extract_paypal_fields(text: str) -> Dict[str, str]:
    """Специальная функция для извлечения полей из PayPal-документов"""
    fields = {}
    text_lower = text.lower()
    
    # Устанавливаем валюту по умолчанию для PayPal
    fields["currency"] = "USD"
    fields["payment_system"] = "PayPal"
    
    # Дата (ищем в форматах, характерных для PayPal)
    date_patterns = [
        r"(\d{2}[./-]\d{2}[./-]\d{2,4})",  # DD.MM.YYYY
        r"(\d{4}[./-]\d{2}[./-]\d{2})",    # YYYY-MM-DD
        r"(\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})",  # 12 january 2023
        r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})"   # 12 января 2023
    ]
    
    for pattern in date_patterns:
        m = re.search(pattern, text_lower)
        if m: 
            fields["date"] = m.group(1)
            break
    
    # Сумма в долларах (специфичные для PayPal шаблоны)
    amount_patterns = [
        r"\$\s*([0-9,]+\.?[0-9]*)",  # $ 123.45
        r"([0-9,]+\.?[0-9]*)\s*usd",  # 123.45 usd
        r"([0-9,]+\.?[0-9]*)\s*USD",  # 123.45 USD
        r"amount\s*[:=]?\s*\$\s*([0-9,]+\.?[0-9]*)",  # amount: $123.45
        r"total\s*[:=]?\s*\$\s*([0-9,]+\.?[0-9]*)",   # total: $123.45
        r"you(?:'ve| have) sent\s*\$\s*([0-9,]+\.?[0-9]*)",  # you've sent $123.45
        r"sent\s*\$\s*([0-9,]+\.?[0-9]*)\s*to"  # sent $123.45 to
    ]
    
    for pattern in amount_patterns:
        m = re.search(pattern, text_lower)
        if m: 
            amount = m.group(1).replace(",", "")  # убираем запятые
            fields["total"] = amount
            break
    
    # ID транзакции
    transaction_patterns = [
        r"transaction\s*id\s*[:=]?\s*([A-Z0-9]+)",
        r"id\s*[:=]?\s*([A-Z0-9]{17})",  # стандартный ID PayPal
        r"tran(saction)?\s*#?\s*[:=]?\s*([A-Z0-9]+)"
    ]
    
    for pattern in transaction_patterns:
        m = re.search(pattern, text_lower)
        if m: 
            fields["transaction_id"] = m.group(1) if len(m.groups()) == 1 else m.group(2)
            break
    
    # Получатель
    recipient_patterns = [
        r"to\s*[:=]?\s*([A-Za-z0-9@\.\-_ ]+)",
        r"recipient\s*[:=]?\s*([A-Za-z0-9@\.\-_ ]+)",
        r"sent to\s*[:=]?\s*([A-Za-z0-9@\.\-_ ]+)"
    ]
    
    for pattern in recipient_patterns:
        m = re.search(pattern, text_lower)
        if m and len(m.group(1)) > 3:  # минимум 3 символа
            fields["recipient"] = m.group(1).strip()
            break
    
    # Статус платежа
    if any(word in text_lower for word in ["completed", "завершен", "выполнен"]):
        fields["status"] = "completed"
    elif any(word in text_lower for word in ["pending", "в обработке", "ожидание"]):
        fields["status"] = "pending"
    
    return fields

def ocr_extract(path: str):
    text = extract_text(path)
    doc_type = classify_document(text)
    fields = extract_fields(text)
    return {"type": doc_type, "fields": fields, "text_preview": text[:1000]}

class OCRModule:
    """Модуль для распознавания текста из чеков"""
    
    @staticmethod
    def normalize_text_for_ocr(text: str) -> str:
        """Нормализация текста для улучшения распознавания сумм и дат"""
        # Заменяем похожие символы на стандартные
        replacements = {
            'o': '0',  # латинская 'o' на ноль
            'O': '0',  # заглавная 'O' на ноль
            'l': '1',  # латинская 'l' на единицу
            'I': '1',  # заглавная 'I' на единицу
            '|': '1',  # вертикальная черта на единицу
            's': '5',  # латинская 's' на пятерку
            'S': '5',  # заглавная 'S' на пятерку
            'б': '6',  # кириллическая 'б' на шестерку
            'в': '8',  # кириллическая 'в' на восьмерку
            'В': '8',  # заглавная 'В' на восьмерку
            'B': '8',  # латинская 'B' на восьмерку
            'д': '9',  # кириллическая 'д' на девятку
        }
        
        normalized = text
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    @staticmethod
    def find_amount_by_context(text: str, context_keywords: list = None) -> Optional[str]:
        """Поиск суммы по контекстным ключевым словам"""
        if context_keywords is None:
            context_keywords = ["сумма", "оплата", "итого", "итог", "к оплате", "перевод"]
        
        lines = text.split('\n')
        text_lower = text.lower()
        
        # Ищем строки с ключевыми словами
        candidate_lines = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in context_keywords):
                candidate_lines.append((i, line))
        
        # Ищем суммы в найденных строках и соседних строках
        for line_idx, line in candidate_lines:
            # Проверяем текущую строку и следующие 2 строки
            for offset in range(3):
                check_idx = line_idx + offset
                if check_idx < len(lines):
                    check_line = lines[check_idx]
                    # Ищем сумму в строке
                    amount_patterns = [
                        r'(\d[\d\s]*[\d])(?:[.,]\d{1,2})?\s*[₽рубрр\.]',
                        r'[₽рубрр\.]\s*(\d[\d\s]*[\d])(?:[.,]\d{1,2})?',
                        r'(\d+[.,]\d{2})',
                    ]
                    
                    for pattern in amount_patterns:
                        matches = re.findall(pattern, check_line.lower())
                        if matches:
                            for match in matches:
                                if isinstance(match, tuple):
                                    match = match[0]
                                
                                clean_match = match.replace(' ', '').replace(',', '.')
                                try:
                                    amount_float = float(clean_match)
                                    if 1 <= amount_float <= 1000000:
                                        return clean_match
                                except:
                                    continue
        
        return None
    
    @staticmethod
    def validate_extracted_amount(amount_str: str, text: str) -> tuple:
        """Валидация извлеченной суммы"""
        try:
            amount = float(amount_str)
            
            # Проверки на реалистичность
            if amount <= 0:
                return False, "Сумма должна быть положительной"
            
            if amount < 0.01:  # Меньше 1 копейки
                return False, "Слишком маленькая сумма"
            
            if amount > 10000000:  # Больше 10 млн
                return False, "Слишком большая сумма"
            
            # Проверка на наличие похожих чисел в тексте
            # (чтобы убедиться, что это действительно сумма, а не часть чего-то другого)
            text_without_spaces = text.replace(' ', '')
            
            # Ищем все числа в тексте
            all_numbers = re.findall(r'\d+[.,]?\d*', text_without_spaces)
            all_numbers_float = []
            
            for num in all_numbers:
                try:
                    num_float = float(num.replace(',', '.'))
                    all_numbers_float.append(num_float)
                except:
                    continue
            
            # Если сумма значительно отличается от других чисел в тексте,
            # это может быть ошибкой
            if len(all_numbers_float) > 1:
                # Вычисляем медиану всех чисел
                sorted_numbers = sorted(all_numbers_float)
                median = sorted_numbers[len(sorted_numbers) // 2]
                
                # Если сумма отличается от медианы более чем в 100 раз
                if amount > 0 and median > 0:
                    ratio = amount / median
                    if ratio > 100 or ratio < 0.01:
                        return False, f"Сумма непропорциональна другим числам в тексте (отношение: {ratio:.2f})"
            
            return True, "OK"
            
        except ValueError:
            return False, "Некорректный формат числа"
    
    @staticmethod
    def extract_amount_with_heuristics(text: str) -> Optional[str]:
        """Извлечение суммы с использованием эвристик"""
        text_lower = text.lower()
        
        # Эвристика 1: Ищем самый крупный денежный оборот
        money_patterns = [
            r'(\d[\d\s]*[\d])(?:[.,]\d{2})?\s*[₽рубр]',
            r'([1-9]\d{0,2}(?:\s?\d{3})*(?:[.,]\d{2})?)\s*[₽рубр]',
        ]
        
        candidates = []
        for pattern in money_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                
                clean_match = match.replace(' ', '').replace(',', '.')
                try:
                    amount = float(clean_match)
                    if 10 <= amount <= 1000000:  # Реалистичный диапазон
                        candidates.append((amount, clean_match))
                except:
                    continue
        
        if candidates:
            # Берем наибольшую сумму (обычно это общая сумма чека)
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
        
        # Эвристика 2: Ищем числа с двумя знаками после запятой
        decimal_pattern = r'(\d+[.,]\d{2})'
        decimal_matches = re.findall(decimal_pattern, text_lower)
        
        decimal_candidates = []
        for match in decimal_matches:
            clean_match = match.replace(',', '.')
            try:
                amount = float(clean_match)
                if 10 <= amount <= 1000000:
                    decimal_candidates.append((amount, clean_match))
            except:
                continue
        
        if decimal_candidates:
            decimal_candidates.sort(key=lambda x: x[0], reverse=True)
            return decimal_candidates[0][1]
        
        return None

    @staticmethod
    def classify_document(text: str) -> str:
        """Классификация документа"""
        t = text.lower()
        
        # Расширяем ключевые слова для российских чеков
        if any(w in t for w in ["чек", "касс", "итог", "сдача", "оплата", "приходный ордер", 
                               "квитанция", "перевод", "оплачено", "исполнено", "покупка", 
                               "операция", "сбп", "система быстрых платежей", "сбербанк"]):
            return "receipt"
        if any(w in t for w in ["счет", "счёт", "накладная", "invoice", "счет-фактура", "р/с"]):
            return "invoice"

        # Ключевые слова для PayPal
        paypal_keywords = ["paypal", "ppl", "pay pal", "пейпал", "пайпал"]
        
        # Проверяем PayPal
        if any(w in t for w in paypal_keywords):
            return "paypal_receipt"
        
        return "unknown"

    def extract_fields(text: str) -> Dict[str, Any]:
        """Извлечение полей из текста"""
        fields = {}
        text_lower = text.lower()
        
        # Определяем тип документа
        doc_type = OCRModule.classify_document(text)
        
        # Для PayPal-документов используем специальную логику
        if doc_type == "paypal_receipt":
            return OCRModule.extract_paypal_fields(text)
        
        # Для российских чеков используем специальную логику
        if doc_type == "receipt":
            return OCRModule.extract_russian_receipt_fields(text)
        
        # Общая логика для других типов
        return OCRModule.extract_common_fields(text)

    @staticmethod
    def extract_russian_receipt_fields_with_font(file_path: str) -> Dict[str, Any]:
        """Извлечение полей из российских чеков с учетом размера шрифта"""
        try:
            # Извлекаем текст с информацией о шрифтах
            font_data = OCRModule.extract_text_with_font_info(file_path)
            full_text = font_data['full_text']
            detailed_text = font_data['detailed_text']
            
            fields = {}
            text_lower = full_text.lower()
            
            # Устанавливаем валюту по умолчанию
            fields["currency"] = "RUB"
            fields["payment_system"] = "СБП" if "сбп" in text_lower or "система быстрых платежей" in text_lower else "Неизвестно"
            
            # Извлекаем дату (существующая логика)
            date_patterns = [
                r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})",
                r"(\d{2}[./-]\d{2}[./-]\d{2,4})",
                r"(\d{4}[./-]\d{2}[./-]\d{2})",
                r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match: 
                    fields["date"] = match.group(1)
                    break
            
            # Поиск суммы с использованием нескольких методов
            amount_candidates = []
            
            # Метод 1: Поиск по размеру шрифта (новый метод)
            font_based = OCRModule.find_amount_by_font_size(detailed_text, full_text)
            if font_based:
                amount, font_size, score = font_based
                amount_candidates.append({
                    'amount': amount,
                    'method': 'font_size',
                    'score': score,
                    'font_size': font_size
                })
            
            # Метод 2: Поиск самого крупного текста
            largest_font = OCRModule.find_amount_by_largest_font(detailed_text)
            if largest_font:
                amount, font_size, confidence = largest_font
                amount_candidates.append({
                    'amount': amount,
                    'method': 'largest_font',
                    'score': font_size * confidence / 100,
                    'font_size': font_size
                })
            
            # Метод 3: Существующая логика (если другие методы не сработали)
            if not amount_candidates:
                existing_result = OCRModule.extract_russian_receipt_fields(full_text)
                if existing_result.get('total'):
                    try:
                        amount_num = float(existing_result['total'])
                        amount_candidates.append({
                            'amount': existing_result['total'],
                            'method': 'existing',
                            'score': 50.0,  # Средний приоритет
                            'font_size': 0
                        })
                    except:
                        pass
            
            # Выбираем лучшего кандидата
            if amount_candidates:
                # Сортируем по score (чем выше, тем лучше)
                amount_candidates.sort(key=lambda x: x['score'], reverse=True)
                best_candidate = amount_candidates[0]
                
                # Валидация суммы
                try:
                    amount_num = float(best_candidate['amount'])
                    
                    # Проверки на реалистичность
                    if amount_num < 0.01 or amount_num > 10000000:
                        fields["total"] = None
                        fields["amount_error"] = f"Нереалистичная сумма: {amount_num}"
                    else:
                        fields["total"] = f"{amount_num:.2f}"
                        fields["amount_method"] = best_candidate['method']
                        fields["font_size_info"] = f"Размер шрифта: {best_candidate.get('font_size', 0)}"
                        
                        # Логирование для отладки
                        logger.info(f"Сумма найдена методом {best_candidate['method']}: {amount_num} руб. Score: {best_candidate['score']:.1f}")
                except ValueError:
                    fields["total"] = None
                    fields["amount_error"] = "Некорректный формат числа"
            else:
                fields["total"] = None
                fields["amount_error"] = "Сумма не найдена"
            
            # Извлечение дополнительных полей (существующая логика)
            number_patterns = [
                r"номер\s+операции[\s:\-]*\s*([A-Za-zА-Яа-я0-9\-]+)",
                r"заказ\s+([A-Za-zА-Яа-я0-9\-]+)",
                r"операция\s+#?\s*([A-Za-zА-Яа-я0-9\-]+)",
                r"№\s*([A-Za-zА-Яа-я0-9\-]+)",
            ]
            
            for pattern in number_patterns:
                m = re.search(pattern, text_lower, re.IGNORECASE)
                if m: 
                    fields["number"] = m.group(1)
                    break
            
            # Статус операции
            if any(word in text_lower for word in ["выполнена", "оплачено", "успешно", "completed"]):
                fields["status"] = "completed"
            elif any(word in text_lower for word in ["в обработке", "ожидание", "pending"]):
                fields["status"] = "pending"
            
            # Логирование результатов
            logger.info(f"Извлечение завершено. Метод: {fields.get('amount_method')}, "
                       f"Сумма: {fields.get('total')}, Дата: {fields.get('date')}")
            
            return fields
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении полей с учетом шрифта: {e}")
            # Fallback к существующему методу
            try:
                return OCRModule.extract_russian_receipt_fields(OCRModule.extract_text_from_image(file_path))
            except:
                return {"currency": "RUB", "total": None, "error": str(e)}

    @staticmethod
    def extract_russian_receipt_fields(text: str) -> Dict[str, Any]:
        """Извлечение полей из российских чеков (особенно СБП)"""
        fields = {}
        text_lines = text.split('\n')
        text_lower = text.lower()
    
        # Устанавливаем валюту по умолчанию
        fields["currency"] = "RUB"
        fields["payment_system"] = "СБП" if "сбп" in text_lower or "система быстрых платежей" in text_lower else "Неизвестно"
    
    # ===== ШАГ 1: ИЗВЛЕЧЕНИЕ ДАТЫ =====
        date_patterns = [
            r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})",
            r"(\d{2}[./-]\d{2}[./-]\d{2,4})",
            r"(\d{4}[./-]\d{2}[./-]\d{2})",
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ]
    
        extracted_date = None
        date_match = None
    
        for pattern in date_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match: 
                extracted_date = match.group(1)
                date_match = match
                fields["date"] = extracted_date
                break
    
    # ===== ШАГ 2: ПОДГОТОВКА ТЕКСТА ДЛЯ ПОИСКА СУММЫ =====
        text_for_amount_search = text_lower
    
    # Если найдена дата, удаляем ее из текста для поиска суммы
        if extracted_date and date_match:
        # Находим точную позицию даты в оригинальном тексте (без учета регистра)
            start_pos = date_match.start()
            end_pos = date_match.end()
        
        # Заменяем дату на специальный маркер, чтобы не нарушать структуру текста
        # Мы используем маркер, который точно не будет совпадать с паттернами суммы
            marker = " _DATE_MARKER_ "
            text_for_amount_search = (
                text_lower[:start_pos] + 
                marker + 
                text_lower[end_pos:]
            )
    
    # ===== ШАГ 3: УЛУЧШЕННОЕ ИЗВЛЕЧЕНИЕ СУММЫ =====
        total_amount = None
    
    # Приоритетные паттерны для сумм (в порядке приоритета)
        amount_patterns = [
        # 1. Сумма операции с явным указанием
            (r"сумма\s+операции[\s:\-]*[^*]*\**\s*([\d\s]+[.,]?\d*)\s*[₽рубр]", 1),
            (r"сумма\s+операции[\s:\-]*\n\s*([\d\s]+[.,]?\d*)\s*[₽рубр]", 1),
        
        # 2. Сумма со словами "итог", "итого", "к оплате"
            (r"(?:итог|итого|к оплате|оплата)[\s:\-]*[^\d]*([\d\s]+[.,]?\d*)\s*[₽рубр]", 2),
            (r"([\d\s]+[.,]?\d*)\s*(?:руб|₽|р\.)\s*(?:итог|итого|к оплате|оплата)", 2),
        
        # 3. Сумма в формате "1 234,56 ₽"
            (r"([\d\s]+[.,]\d{2})\s*[₽рубр]", 3),
        
        # 4. Сумма с отрицательным знаком (возврат)
            (r"-\s*([\d\s]+[.,]?\d*)\s*[₽рубр]", 4),
        
        # 5. Сумма в формате с операцией "→"
            (r"([\d\s,]+)₽\s*→", 5),
        
        # 6. Общий паттерн для сумм (резервный, самый низкий приоритет)
            (r"([\d\s]+[.,]?\d*)\s*[₽рубр]", 6),
        ]
    
    # Собираем все найденные кандидаты в суммы
        amount_candidates = []
    
        for pattern, priority in amount_patterns:
            matches = re.findall(pattern, text_for_amount_search)
            if matches:
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]  # Если группа захватила несколько элементов
                
                # Очищаем строку
                    clean_match = str(match).strip()
                    clean_match = clean_match.replace(' ', '').replace(',', '.')
                
                # Проверяем, не является ли это фрагментом даты
                # (дополнительная проверка на случай если дата не была удалена)
                    if re.search(r'^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$', clean_match):
                        continue
                
                # Проверяем, не является ли это слишком маленьким числом
                    try:
                        amount_float = float(clean_match)
                    
                    # Фильтрация нереалистичных сумм
                        if amount_float < 1:  # Меньше 1 рубля - вероятно, это копейки или ошибка
                            continue
                        if amount_float > 10000000:  # Больше 10 млн - нереалистично для чека
                            continue
                    
                        amount_candidates.append({
                            'value': clean_match,
                            'amount': amount_float,
                            'priority': priority,
                            'pattern': pattern
                        })
                    
                    except ValueError:
                        continue
    
    # Выбираем лучшего кандидата
        if amount_candidates:
        # Сначала сортируем по приоритету (чем меньше число, тем выше приоритет)
        # Затем по величине суммы (берем наибольшую из кандидатов с одинаковым приоритетом)
            amount_candidates.sort(key=lambda x: (x['priority'], -x['amount']))
            total_amount = amount_candidates[0]['value']
    
    # ===== ШАГ 4: АЛЬТЕРНАТИВНЫЕ МЕТОДЫ ЕСЛИ СУММА НЕ НАЙДЕНА =====
        if not total_amount:
        # Метод 1: Ищем сумму по контексту - ищем строки, содержащие "₽" или "руб"
            rubl_lines = [line for line in text_lines if any(c in line for c in ['₽', 'руб', 'р.'])]
        
            for line in rubl_lines:
            # Ищем числа с разделителями тысяч
                line_lower = line.lower()
            
            # Паттерн для чисел с пробелами (1 000, 10 000 и т.д.)
                pattern = r'(\d[\d\s]*[\d])(?:[.,]\d{2})?\s*[₽рубрр\.]'
                matches = re.findall(pattern, line_lower)
            
                if matches:
                    for match in matches:
                        clean_match = match.replace(' ', '').replace(',', '.')
                        try:
                            amount_float = float(clean_match)
                            if 10 <= amount_float <= 1000000:  # Реалистичный диапазон для чека
                                total_amount = clean_match
                                break
                        except:
                            continue
                
                    if total_amount:
                        break
    
    # ===== ШАГ 5: ПРОВЕРКА И ВАЛИДАЦИЯ РЕЗУЛЬТАТА =====
        if total_amount:
            try:
            # Преобразуем в число для проверки
                amount_num = float(total_amount)
            
            # Дополнительная проверка: сумма должна быть реалистичной для чека
                if amount_num < 0.01:  # Меньше 1 копейки
                    logger.warning(f"Слишком маленькая сумма в чеке: {amount_num}")
                    fields["total"] = None
                elif amount_num > 10000000:  # Больше 10 млн
                    logger.warning(f"Слишком большая сумма в чеке: {amount_num}")
                    fields["total"] = None
                else:
                # Округляем до 2 знаков после запятой
                    fields["total"] = f"{amount_num:.2f}"
            except ValueError:
                logger.error(f"Некорректное значение суммы: {total_amount}")
                fields["total"] = None
        else:
            fields["total"] = None
            logger.warning("Сумма не найдена в чеке")
    
    # ===== ШАГ 6: ИЗВЛЕЧЕНИЕ ДОПОЛНИТЕЛЬНЫХ ПОЛЕЙ =====
    # Извлечение номера операции/заказа
        number_patterns = [
            r"номер\s+операции[\s:\-]*\s*([A-Za-zА-Яа-я0-9\-]+)",
            r"заказ\s+([A-Za-zА-Яа-я0-9\-]+)",
            r"операция\s+#?\s*([A-Za-zА-Яа-я0-9\-]+)",
            r"№\s*([A-Za-zА-Яа-я0-9\-]+)",
        ]
    
        for pattern in number_patterns:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m: 
                fields["number"] = m.group(1)
                break
    
    # Извлечение магазина/продавца
        shop_patterns = [
            r"магазин[\s:\-]*\s*([^\n]+)",
            r"o[б6]щ[еc]ство[^\n]*",
            r"получатель[\s:\-]*\s*([^\n]+)",
        ]
    
        for pattern in shop_patterns:
            m = re.search(pattern, text_lower, re.IGNORECASE)
            if m: 
                fields["shop"] = m.group(0)[:100]  # Ограничиваем длину
                break
    
    # Статус операции
        if any(word in text_lower for word in ["выполнена", "оплачено", "успешно", "completed"]):
            fields["status"] = "completed"
        elif any(word in text_lower for word in ["в обработке", "ожидание", "pending"]):
            fields["status"] = "pending"
    
    # ===== ШАГ 7: ЛОГГИРОВАНИЕ И ОТЛАДКА =====
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Извлечено из чека:")
            logger.debug(f"  Дата: {fields.get('date')}")
            logger.debug(f"  Сумма: {fields.get('total')}")
            logger.debug(f"  Валюта: {fields.get('currency')}")
            logger.debug(f"  Платежная система: {fields.get('payment_system')}")
        
            if extracted_date and total_amount:
                logger.debug(f"  Проверка: дата '{extracted_date}' не должна совпадать с суммой '{total_amount}'")
    
        return fields

    @staticmethod
    def extract_russian_receipt_fields_v2(text: str) -> Dict[str, Any]:
        """Улучшенная версия извлечения полей из российских чеков"""
        # Нормализуем текст
        normalized_text = OCRModule.normalize_text_for_ocr(text)
        
        # Извлекаем дату
        fields = {}
        # ===== ИЗВЛЕЧЕНИЕ ДАТЫ =====
        date_patterns = [
            r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})",
            r"(\d{2}[./-]\d{2}[./-]\d{2,4})",
            r"(\d{4}[./-]\d{2}[./-]\d{2})",
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ]
    
        extracted_date = None
        date_match = None
    
        for pattern in date_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match: 
                extracted_date = match.group(1)
                date_match = match
                fields["date"] = extracted_date
                break
        # Используем несколько методов для извлечения суммы
        amount_candidates = []
        
        # Метод 1: Основной метод (удаление даты из текста)
        amount1 = OCRModule._extract_amount_without_date(normalized_text, fields.get('date'))
        
        # Метод 2: По контексту
        amount2 = OCRModule.find_amount_by_context(normalized_text)
        
        # Метод 3: Эвристики
        amount3 = OCRModule.extract_amount_with_heuristics(normalized_text)
        
        # Собираем все кандидаты
        if amount1:
            amount_candidates.append(('method1', amount1))
        if amount2:
            amount_candidates.append(('method2', amount2))
        if amount3:
            amount_candidates.append(('method3', amount3))
        
        # Выбираем лучшего кандидата
        if amount_candidates:
            # Проверяем каждого кандидата
            valid_candidates = []
            for method, amount in amount_candidates:
                is_valid, message = OCRModule.validate_extracted_amount(amount, normalized_text)
                if is_valid:
                    valid_candidates.append((method, amount, message))
            
            if valid_candidates:
                # Предпочитаем метод 1 (самый надежный)
                for method, amount, message in valid_candidates:
                    if method == 'method1':
                        fields['total'] = amount
                        fields['amount_source'] = method
                        break
                else:
                    # Если метод 1 не подошел, берем первый валидный
                    fields['total'] = valid_candidates[0][1]
                    fields['amount_source'] = valid_candidates[0][0]
            else:
                fields['total'] = None
                fields['amount_source'] = 'none'
        else:
            fields['total'] = None
            fields['amount_source'] = 'none'
        
        return fields

    @staticmethod
    def extract_common_fields(text: str) -> Dict[str, Any]:
        """Извлечение полей из других типов документов"""
        fields = {}
        text_lower = text.lower()
        
        # Дата
        date_patterns = [
            r"(\d{2}[./-]\d{2}[./-]\d{2,4})",
            r"(\d{4}[./-]\d{2}[./-]\d{2})",
            r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})",
        ]
        
        for pattern in date_patterns:
            m = re.search(pattern, text_lower)
            if m: 
                fields["date"] = m.group(1)
                break
        
        # Сумма
        amount_patterns = [
            r"(?:итог|сумма|к оплате|total|amount)\s*[:=]?\s*([\d\s]+[.,][\d]{2})",
            r"\$\s*([\d,]+\.?\d*)",
            r"([\d\s]+[.,]\d{2})\s*(?:руб|₽|р\.)",
        ]
        
        for pattern in amount_patterns:
            m = re.search(pattern, text_lower)
            if m: 
                amount = m.group(1).replace(',', '.').replace(' ', '')
                fields["total"] = amount
                break
        
        # Валюта
        if '₽' in text or 'руб' in text_lower:
            fields["currency"] = "RUB"
        elif '$' in text or 'usd' in text_lower:
            fields["currency"] = "USD"
        elif '€' in text or 'eur' in text_lower:
            fields["currency"] = "EUR"
        else:
            fields["currency"] = "RUB"
        
        return fields

    @staticmethod
    def extract_paypal_fields(text: str) -> dict:
        """Извлечение полей из PayPal-документов"""
        fields = {}
        text_lower = text.lower()
        
        # Устанавливаем валюту по умолчанию для PayPal
        fields["currency"] = "USD"
        fields["payment_system"] = "PayPal"
        
        # Дата
        date_patterns = [
            r"(\d{2}[./-]\d{2}[./-]\d{2,4})",  # DD.MM.YYYY
            r"(\d{4}[./-]\d{2}[./-]\d{2})",    # YYYY-MM-DD
            r"(\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})",  # 12 january 2023
            r"(\d{1,2}\s+(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s+\d{4})"   # 12 января 2023
        ]
        
        for pattern in date_patterns:
            m = re.search(pattern, text_lower)
            if m: 
                fields["date"] = m.group(1)
                break
        
        # Сумма
        amount_patterns = [
            r"\$\s*([0-9,]+\.?[0-9]*)",  # $ 123.45
            r"([0-9,]+\.?[0-9]*)\s*usd",  # 123.45 usd
            r"([0-9,]+\.?[0-9]*)\s*USD",  # 123.45 USD
            r"amount\s*[:=]?\s*\$\s*([0-9,]+\.?[0-9]*)",  # amount: $123.45
            r"total\s*[:=]?\s*\$\s*([0-9,]+\.?[0-9]*)",   # total: $123.45
            r"you(?:'ve| have) sent\s*\$\s*([0-9,]+\.?[0-9]*)",  # you've sent $123.45
            r"sent\s*\$\s*([0-9,]+\.?[0-9]*)\s*to"  # sent $123.45 to
        ]
        
        for pattern in amount_patterns:
            m = re.search(pattern, text_lower)
            if m: 
                amount = m.group(1).replace(",", "")  # убираем запятые
                fields["total"] = amount
                break
        
        # ID транзакции
        transaction_patterns = [
            r"transaction\s*id\s*[:=]?\s*([A-Z0-9]+)",
            r"id\s*[:=]?\s*([A-Z0-9]{17})",  # стандартный ID PayPal
            r"tran(saction)?\s*#?\s*[:=]?\s*([A-Z0-9]+)"
        ]
        
        for pattern in transaction_patterns:
            m = re.search(pattern, text_lower)
            if m: 
                fields["transaction_id"] = m.group(1) if len(m.groups()) == 1 else m.group(2)
                break
        
        # Получатель
        recipient_patterns = [
            r"to\s*[:=]?\s*([A-Za-z0-9@\.\-_ ]+)",
            r"recipient\s*[:=]?\s*([A-Za-z0-9@\.\-_ ]+)",
            r"sent to\s*[:=]?\s*([A-Za-z0-9@\.\-_ ]+)"
        ]
        
        for pattern in recipient_patterns:
            m = re.search(pattern, text_lower)
            if m and len(m.group(1)) > 3:  # минимум 3 символа
                fields["recipient"] = m.group(1).strip()
                break
        
        # Статус платежа
        if any(word in text_lower for word in ["completed", "завершен", "выполнен"]):
            fields["status"] = "completed"
        elif any(word in text_lower for word in ["pending", "в обработке", "ожидание"]):
            fields["status"] = "pending"
        
        return fields

    @staticmethod
    async def extract_text_from_image(file_path: str) -> str:
        """Извлечение текста из изображения (заглушка, нужно установить pytesseract)"""
        try:
            # Попробуем использовать pytesseract если установлен
            try:
                import pytesseract
                from PIL import Image
                
                image = Image.open(file_path)
                text = pytesseract.image_to_string(image, lang='rus+eng')
                return text
            except ImportError:
                # Если pytesseract не установлен, используем простую заглушку
                return "Текст не распознан. Установите pytesseract для распознавания."
                
        except Exception as e:
            logger.error(f"Ошибка OCR: {e}")
            return f"Ошибка распознавания: {str(e)}"

    @staticmethod
    async def extract_text_from_pdf(file_path: str) -> str:
        """Извлечение текста из PDF (заглушка)"""
        try:
            # Для PDF нужен дополнительный модуль
            return "Текст из PDF (не реализовано)"
        except Exception as e:
            logger.error(f"Ошибка OCR PDF: {e}")
            return f"Ошибка распознавания PDF: {str(e)}"

    @staticmethod
    async def ocr_extract_with_font(file_path: str, use_font_analysis: bool = True) -> Dict[str, Any]:
        """Основная функция OCR с поддержкой анализа шрифта"""
        try:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
                if use_font_analysis:
                    # Используем улучшенный метод с анализом шрифта
                    font_data = OCRModule.extract_text_with_font_info(file_path)
                    text = font_data['full_text']
                else:
                    text = await OCRModule.extract_text_from_image(file_path)
            elif file_ext == '.pdf':
                text = await OCRModule.extract_text_from_pdf(file_path)
            else:
                text = "Неподдерживаемый формат файла"
            
            doc_type = OCRModule.classify_document(text)
            
            if doc_type == "receipt" and use_font_analysis and file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
                # Используем метод с анализом шрифта для изображений чеков
                fields = OCRModule.extract_russian_receipt_fields_with_font(file_path)
            elif doc_type == "paypal_receipt":
                fields = OCRModule.extract_paypal_fields(text)
            elif doc_type == "receipt":
                fields = OCRModule.extract_russian_receipt_fields(text)
            else:
                fields = OCRModule.extract_common_fields(text)
            
            return {
                "type": doc_type,
                "fields": fields,
                "text_preview": text[:1000] if text else "Нет текста",
                "raw_text": text,
                "font_analysis_used": use_font_analysis and doc_type == "receipt"
            }
        except Exception as e:
            logger.error(f"Ошибка в OCR с анализом шрифта: {e}")
            return {
                "type": "error",
                "fields": {},
                "text_preview": f"Ошибка: {str(e)}",
                "raw_text": "",
                "font_analysis_used": False
            }

    @staticmethod
    async def ocr_extract(file_path: str) -> Dict[str, Any]:
        """Основная функция OCR"""
        try:
            # Определяем тип файла
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']:
                text = await OCRModule.extract_text_from_image(file_path)
            elif file_ext == '.pdf':
                text = await OCRModule.extract_text_from_pdf(file_path)
            else:
                text = "Неподдерживаемый формат файла"
            
            # Классифицируем документ
            doc_type = OCRModule.classify_document(text)
            
            # Извлекаем поля
            fields = OCRModule.extract_fields(text)
            
            return {
                "type": doc_type,
                "fields": fields,
                "text_preview": text[:1000] if text else "Нет текста",
                "raw_text": text
            }
        except Exception as e:
            logger.error(f"Ошибка в OCR: {e}")
            return {
                "type": "error",
                "fields": {},
                "text_preview": f"Ошибка: {str(e)}",
                "raw_text": ""
            }
    @staticmethod
    def extract_text_with_font_info(file_path: str) -> dict:
        """Извлечение текста с информацией о размере шрифта"""
        try:
            import pytesseract
            from PIL import Image
            import pandas as pd
            
            image = Image.open(file_path)
            
            # Получаем детальную информацию о тексте (включая размеры)
            data = pytesseract.image_to_data(
                image, 
                lang='rus+eng',
                output_type=pytesseract.Output.DICT
            )
            
            # Собираем текст с информацией о размере
            text_with_font = []
            n_boxes = len(data['level'])
            
            for i in range(n_boxes):
                if int(data['conf'][i]) > 0:  # Только уверенные распознавания
                    text = data['text'][i].strip()
                    if text:  # Не пустой текст
                        text_with_font.append({
                            'text': text,
                            'height': data['height'][i],
                            'width': data['width'][i],
                            'font_size': max(data['height'][i], data['width'][i] // 2),  # Приблизительный размер шрифта
                            'left': data['left'][i],
                            'top': data['top'][i],
                            'conf': data['conf'][i]
                        })
            
            # Получаем полный текст для обратной совместимости
            full_text = pytesseract.image_to_string(image, lang='rus+eng')
            
            return {
                'full_text': full_text,
                'detailed_text': text_with_font,
                'image_width': image.width,
                'image_height': image.height
            }
            
        except ImportError:
            # Если pytesseract не установлен, возвращаем простой текст
            return {
                'full_text': "Текст не распознан. Установите pytesseract.",
                'detailed_text': [],
                'image_width': 0,
                'image_height': 0
            }
        except Exception as e:
            logger.error(f"Ошибка при извлечении текста с информацией о шрифте: {e}")
            return {
                'full_text': f"Ошибка: {str(e)}",
                'detailed_text': [],
                'image_width': 0,
                'image_height': 0
            }

    @staticmethod
    def find_amount_by_font_size(detailed_text: list, full_text: str) -> Optional[tuple]:
        """Поиск суммы по размеру шрифта"""
        if not detailed_text:
            return None
        
        # Ищем числа и суммы в тексте с информацией о шрифтах
        amount_candidates = []
        
        # Собираем все элементы с числами
        for item in detailed_text:
            text = item['text']
            font_size = item['font_size']
            
            # Паттерны для сумм
            amount_patterns = [
                r'(\d[\d\s]*[\d])(?:[.,]\d{1,2})?\s*[₽рубрр\.]',
                r'[₽рубрр\.]\s*(\d[\d\s]*[\d])(?:[.,]\d{1,2})?',
                r'(\d+[.,]\d{2})',
                r'(\d[\d\s,]+)(?=\s*(?:руб|₽|р\.|USD|\$|EUR|€))',
            ]
            
            for pattern in amount_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    for match in matches:
                        if isinstance(match, tuple):
                            match = match[0]
                        
                        clean_match = match.replace(' ', '').replace(',', '.')
                        
                        try:
                            amount_float = float(clean_match)
                            # Проверяем реалистичность суммы
                            if 1 <= amount_float <= 1000000:
                                # Учитываем размер шрифта
                                score = font_size * item['conf'] / 100
                                
                                # Проверяем контекст - ищем ключевые слова рядом
                                context_score = 0
                                if re.search(r'(итог|итого|оплата|сумма|всего|к\s*оплате)', 
                                           text, re.IGNORECASE):
                                    context_score = 1.5
                                
                                amount_candidates.append({
                                    'text': text,
                                    'amount': amount_float,
                                    'clean_match': clean_match,
                                    'font_size': font_size,
                                    'score': score * (1 + context_score),
                                    'item': item
                                })
                        except ValueError:
                            continue
        
        if amount_candidates:
            # Сортируем по "весу" (размер шрифта * уверенность * контекст)
            amount_candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # Возвращаем лучшего кандидата
            best = amount_candidates[0]
            return best['clean_match'], best['font_size'], best['score']
        
        return None

    @staticmethod
    def find_amount_by_largest_font(detailed_text: list) -> Optional[tuple]:
        """Ищет самый крупный текст, который может быть суммой"""
        if not detailed_text:
            return None
        
        # Сортируем по размеру шрифта
        sorted_by_size = sorted(detailed_text, key=lambda x: x['font_size'], reverse=True)
        
        # Проверяем топ-5 самых крупных текстов
        for item in sorted_by_size[:5]:
            text = item['text']
            font_size = item['font_size']
            
            # Усиленные паттерны для сумм
            amount_patterns = [
                r'([1-9]\d{0,2}(?:\s?\d{3})*(?:[.,]\d{2})?)\s*[₽рубр]',
                r'(\d+[.,]\d{2})\s*(?:руб|₽|р\.)',
                r'(?:итог|итого|оплата|сумма|всего|к\s*оплате)[\s:]*([\d\s.,]+)',
                r'([\d\s,]+)(?=\s*(?:рублей|рубля|руб|₽|р\.))',
                r'(\d+[.,]\d{2})',  # Просто число с двумя знаками после запятой
            ]
            
            for pattern in amount_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    for match in matches:
                        if isinstance(match, tuple):
                            match = match[0]
                        
                        clean_match = str(match).strip()
                        clean_match = clean_match.replace(' ', '').replace(',', '.')
                        
                        # Проверяем, что это число
                        try:
                            amount_float = float(clean_match)
                            if 1 <= amount_float <= 1000000:
                                return clean_match, font_size, item['conf']
                        except ValueError:
                            continue
        
        return None