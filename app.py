import os
import pymysql
from flask import Flask, render_template, jsonify, request, send_file
from datetime import datetime, timedelta
import json
from apscheduler.schedulers.background import BackgroundScheduler
import io
import csv

app = Flask(__name__)

# Инициализация планировщика
scheduler = BackgroundScheduler()
scheduler.start()

test = False

connection_params = {}

if test:
    connection_params = {
        'host': 'caboose.proxy.rlwy.net',
        'user': 'root',
        'password': 'DDpsjGWjNaukHWigpSFLsrGGQWcvErmy',
        'database': 'railway',
        'port': 48502,
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }
else:
    connection_params = {
        'host': os.getenv('MYSQLHOST', 'mysql.railway.internal'),
        'user': os.getenv('MYSQLUSER', 'root'),
        'password': os.getenv('MYSQLPASSWORD', 'DDpsjGWjNaukHWigpSFLsrGGQWcvErmy'),
        'database': os.getenv('MYSQLDATABASE', 'railway'),
        'port': int(os.getenv('MYSQLPORT', 3306)),
        'charset': 'utf8mb4',
        'cursorclass': pymysql.cursors.DictCursor
    }

def get_db_connection():
    return pymysql.connect(**connection_params)

def save_user_stats():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as active FROM users WHERE status = TRUE")
            active_users = cursor.fetchone()['active']
            
            cursor.execute("SELECT id FROM users WHERE status = TRUE")
            active_user_ids = [row['id'] for row in cursor.fetchall()]
            
            if active_user_ids:
                values = [(user_id, datetime.utcnow()) for user_id in active_user_ids]
                cursor.executemany(
                    "INSERT IGNORE INTO unique_users (id, timestamp) VALUES (%s, %s)",
                    values
                )
            
            cursor.execute("SELECT COUNT(*) as total_rows FROM unique_users")
            result = cursor.fetchone()
            total_rows = result['total_rows']
            
            utc_now = datetime.utcnow()
            cursor.execute("""
                INSERT INTO user_history (timestamp, total_users, active_users, unique_users)
                VALUES (%s, %s, %s, %s)
            """, (utc_now, total_users, active_users, total_rows))
            
            # Сохраняем лучшие данные за день в late_history (только дата, без времени)
            today = utc_now.date()
            cursor.execute("""
                SELECT MAX(active_users) as max_active 
                FROM user_history 
                WHERE DATE(timestamp) = %s
            """, (today,))
            max_active = cursor.fetchone()['max_active']
            
            if max_active:
                cursor.execute("""
                    SELECT total_users, active_users, unique_users
                    FROM user_history 
                    WHERE DATE(timestamp) = %s AND active_users = %s
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (today, max_active))
                best_record = cursor.fetchone()
                
                # Используем только дату (без времени) для timestamp
                cursor.execute("""
                    INSERT INTO late_history (timestamp, total_users, active_users, unique_users)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        total_users = VALUES(total_users),
                        active_users = VALUES(active_users)
                """, (today, best_record['total_users'], best_record['active_users'],best_record['unique_users']))
            
            conn.commit()
    except Exception as e:
        print(f"Ошибка при сохранении статистики: {e}")
    finally:
        conn.close()
        
scheduler.add_job(
    func=save_user_stats,
    trigger='interval',
    minutes=1,
    id='save_user_stats_job'
)

def init_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            
            # Создаем таблицу unique_users, если ее нет
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS unique_users (
                    id INT PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    UNIQUE KEY (id)  
                )
            """)
            
            # Создаем таблицу user_history, если ее нет
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    total_users INT NOT NULL,
                    active_users INT NOT NULL,
                    unique_users INT NOT NULL
                )
            """)
            
            # Создаем таблицу late_history, если ее нет
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS late_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp DATETIME NOT NULL,
                    total_users INT NOT NULL,
                    active_users INT NOT NULL,
                    UNIQUE KEY (timestamp),
                    unique_users INT NOT NULL
                )
            """)
            
            # Создаем индексы для user_history
            cursor.execute("""
                SELECT COUNT(1) as index_exists 
                FROM INFORMATION_SCHEMA.STATISTICS 
                WHERE table_schema = DATABASE() 
                AND table_name = 'user_history' 
                AND index_name = 'idx_timestamp'
            """)
            result = cursor.fetchone()
            
            if result['index_exists'] == 0:
                cursor.execute("CREATE INDEX idx_timestamp ON user_history (timestamp)")
            
            cursor.execute("""
                SELECT COUNT(1) as index_exists 
                FROM INFORMATION_SCHEMA.STATISTICS 
                WHERE table_schema = DATABASE() 
                AND table_name = 'user_history' 
                AND index_name = 'idx_active_users'
            """)
            result = cursor.fetchone()
            
            if result['index_exists'] == 0:
                cursor.execute("CREATE INDEX idx_active_users ON user_history (active_users)")
            
            conn.commit()
    except Exception as e:
        print(f"Ошибка при инициализации БД: {e}")
    finally:
        conn.close()

def cleanup_old_data():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Удаляем старые данные из user_history (оставляем только последние 24 часа)
            cursor.execute("""
                DELETE FROM user_history 
                WHERE timestamp < %s
            """, (datetime.utcnow() - timedelta(hours=24),))
            
            cursor.execute("""
                DELETE FROM unique_users 
                WHERE timestamp < %s
            """, (datetime.utcnow() - timedelta(hours=24),))
            
            # Удаляем старые данные из late_history (оставляем только последние 30 дней)
            cursor.execute("""
                DELETE FROM late_history 
                WHERE timestamp < %s
            """, (datetime.utcnow() - timedelta(days=30),))
            
            conn.commit()
    except Exception as e:
        print(f"Ошибка при очистке старых данных: {e}")
    finally:
        conn.close()

def get_user_stats(hours=24):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Изменено: выбираем подписки только активных пользователей\
            event_counts = {
                "Алтарь": 0,
                "Вулкан": 0,
                "Маяк убийца": 0,
                "Адская резня": 0,
                "Сундук смерти": 0,
                "Метеоритный дождь": 0,
                "Мистический сундук": 0
                }
            total_active_subs = 0
            try:
                cursor.execute("SELECT events FROM users WHERE status = TRUE")
                subscriptions = cursor.fetchall()
                
                for user in subscriptions:
                    try:
                        subs = json.loads(user['events'])
                        for sub, active in subs.items():
                            if active:
                                event_counts[sub] += 1
                        total_active_subs += 1
                    except json.JSONDecodeError:
                        continue
            except:
                pass

            mine_counts = {
                'Обычная': 0,
                'Мифическая': 0,
                'Легендарная': 0
            }
            
            try:
                cursor.execute("SELECT mine FROM users WHERE status = TRUE")
                subscriptions = cursor.fetchall()
    
                
                for user in subscriptions:
                    try:
                        subs = json.loads(user['mine'])
                        for sub, active in subs.items():
                            if active:
                                mine_counts[sub] += 1
                    except json.JSONDecodeError:
                        continue
            except:
                pass
            # Остальной код остается без изменений
            if hours == 1:
                time_format = "%H:%M"
                group_interval = 120
                points = 30
                query_table = "user_history"
            elif hours == 24:
                time_format = "%H:%M"
                group_interval = 3600
                points = 24
                query_table = "user_history"
            elif hours == 168:
                time_format = "%Y-%m-%d"
                group_interval = 86400
                points = 7
                query_table = "late_history"
            else:
                time_format = "%Y-%m-%d"
                group_interval = 86400
                points = 30
                query_table = "late_history"
            
            start_time = datetime.utcnow() - timedelta(hours=hours)
            
            query = f"""
                SELECT 
                    FROM_UNIXTIME(MIN(UNIX_TIMESTAMP(timestamp))) as timestamp,
                    AVG(total_users) as total_users,
                    AVG(active_users) as active_users,
                    AVG(unique_users) as unique_users
                FROM (
                    SELECT 
                        timestamp,
                        total_users,
                        active_users,
                        unique_users,
                        FLOOR(UNIX_TIMESTAMP(timestamp) / %s) as time_group
                    FROM {query_table}
                    WHERE timestamp >= %s
                ) as grouped_data
                GROUP BY time_group
                ORDER BY time_group ASC
                LIMIT %s
            """
            
            cursor.execute(query, (group_interval, start_time, points))
            
            history = []
            for row in cursor.fetchall():
                utc_time = row['timestamp']
                history.append({
                    'time': utc_time.strftime('%H:%M'),
                    'date': utc_time.strftime('%Y-%m-%d'),
                    'datetime': utc_time.strftime('%Y-%m-%d %H:%M'),
                    'total_users': round(float(row['total_users'])),
                    'active_users': round(float(row['active_users'])),
                    'unique_users': round(float(row['unique_users']))
                })
            
            cursor.execute("SELECT COUNT(*) as total FROM users")
            total_users = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as active FROM users WHERE status = TRUE")
            active_users = cursor.fetchone()['active']
            
            
            
            return {
                'status': 'success',
                'data': {
                    'total_users': total_users,
                    'active_users': active_users,
                    'event': event_counts,
                    'mine' : mine_counts,
                    'total_active_subs': total_active_subs,
                    'history': history
                }
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    finally:
        conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def api_stats():
    try:
        hours = int(request.args.get('hours', 24))
        cleanup_old_data()
        stats = get_user_stats(hours)
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/download_db')
def download_db():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Получаем список таблиц
            cursor.execute("SHOW TABLES")
            tables = [table['Tables_in_railway'] for table in cursor.fetchall()]
            
            # Создаем SQL-дамп
            output = io.StringIO()
            
            # Добавляем заголовок
            output.write("-- MySQL dump 10.13\n")
            output.write(f"-- Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n")
            output.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")
            
            # Для каждой таблицы сохраняем структуру и данные
            for table in tables:
                # Получаем структуру таблицы
                cursor.execute(f"SHOW CREATE TABLE {table}")
                create_table = cursor.fetchone()['Create Table']
                output.write(f"--\n-- Table structure for table `{table}`\n--\n\n")
                output.write(f"{create_table};\n\n")
                
                # Получаем данные таблицы
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                if rows:
                    output.write(f"--\n-- Dumping data for table `{table}`\n--\n\n")
                    for row in rows:
                        columns = ', '.join([f"`{k}`" for k in row.keys()])
                        values = []
                        for v in row.values():
                            if v is None:
                                values.append('NULL')
                            elif isinstance(v, (int, float)):
                                values.append(str(v))
                            else:
                                # Экранируем специальные символы
                                val = str(v).replace('\\', '\\\\').replace("'", "''")
                                values.append(f"'{val}'")
                        
                        output.write(f"INSERT INTO `{table}` ({columns}) VALUES ({', '.join(values)});\n")
                    output.write("\n")
            
            output.write("SET FOREIGN_KEY_CHECKS = 1;\n")
            output.write("-- Dump completed\n")
            
            # Возвращаем файл для скачивания
            output.seek(0)
            return send_file(
                io.BytesIO(output.getvalue().encode('utf-8')),
                mimetype='application/sql',
                as_attachment=True,
                download_name=f'database_dump_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.sql'
            )
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    finally:
        conn.close()

@app.route('/api/upload_db', methods=['POST'])
def upload_db():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Файл не найден'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'Файл не выбран'}), 400
    
    conn = get_db_connection()
    try:
        content = file.read().decode('utf-8')
        
        # Разделяем SQL-запросы
        queries = [q.strip() for q in content.split(';') if q.strip()]
        
        with conn.cursor() as cursor:
            # 1. Отключаем проверку внешних ключей
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            # 2. Получаем список всех таблиц
            cursor.execute("SHOW TABLES")
            tables = [table[f"Tables_in_{connection_params['database']}"] for table in cursor.fetchall()]
            
            # 3. Удаляем все существующие таблицы
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
            
            # 4. Выполняем все запросы из файла
            for query in queries:
                try:
                    if query.strip():  # Пропускаем пустые запросы
                        cursor.execute(query)
                except pymysql.Error as e:
                    print(f"Ошибка при выполнении запроса: {query}\nОшибка: {e}")
                    continue
            
            # 5. Включаем проверку внешних ключей
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            
            conn.commit()
        
        return jsonify({'status': 'success', 'message': 'База данных полностью перезаписана'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
