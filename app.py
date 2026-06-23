######################################
# VERSUS skeleton app.py
# CS460 Final Project
######################################
# Covers the core: register/login, create bracket, browse, view.
# Students extend with: predictions, voting, round-closing (stored
# procedure), triggers, leaderboard (window functions), recursive CTE,
# follows, comments, indexes.
###################################################

from flask import Flask, request, render_template, redirect, url_for
import mysql.connector
import flask_login
import datetime
import bcrypt

app = Flask(__name__)
app.secret_key = 'super secret string'  # Change this!

# These will need to be changed according to your credentials.
DB_USER     = 'root'
DB_PASSWORD = 'your_password'
DB_NAME     = 'versus'
DB_HOST     = 'localhost'

def get_conn():
	return mysql.connector.connect(
		host=DB_HOST,
		user=DB_USER,
		password=DB_PASSWORD,
		database=DB_NAME,
		autocommit=False,
	)


# begin code used for login
login_manager = flask_login.LoginManager()
login_manager.init_app(app)


def getUserList():
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute("SELECT username from Users")
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return rows


class User(flask_login.UserMixin):
	pass


@login_manager.user_loader
def user_loader(username):
	users = getUserList()
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	return user


@login_manager.request_loader
def request_loader(request):
	users = getUserList()
	username = request.form.get('username')
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute("SELECT password FROM Users WHERE username = %s", (username,))
	data = cursor.fetchall()
	cursor.close()
	conn.close()
	if not data:
		return user
	pwd_hash = data[0][0].encode('utf-8') if isinstance(data[0][0], str) else data[0][0]
	user.is_authenticated = bcrypt.checkpw(
		request.form.get('password', '').encode('utf-8'), pwd_hash)
	return user


'''
A new page looks like this:
@app.route('new_page_name')
def new_page_function():
	return new_page_html
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'GET':
		return render_template('login.html')

	username = request.form['username']
	password = request.form['password']
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute("SELECT password FROM Users WHERE username = %s", (username,))
	data = cursor.fetchall()
	cursor.close()
	conn.close()

	if data:
		pwd_hash = data[0][0].encode('utf-8') if isinstance(data[0][0], str) else data[0][0]
		if bcrypt.checkpw(password.encode('utf-8'), pwd_hash):
			user = User()
			user.id = username
			flask_login.login_user(user)
			return redirect(url_for('home'))

	return render_template('login.html', error='Invalid username or password.')


@login_manager.unauthorized_handler
def unauthorized_handler():
	return render_template('unauth.html')


# you can specify specific methods (GET/POST) in the function header instead
# of inside the function body
@app.route("/register", methods=['GET'])
def register():
	return render_template('register.html')


@app.route("/register", methods=['POST'])
def register_user():
	username = request.form.get('username', '').strip()
	email    = request.form.get('email', '').strip()
	password = request.form.get('password', '')
	bio      = request.form.get('bio', '').strip()

	if not username or not email or not password:
		return render_template('register.html', error='All fields are required.')
	if not isUsernameUnique(username):
		return render_template('register.html', error='Username already taken.')
	if not isEmailUnique(email):
		return render_template('register.html', error='Email already registered.')

	pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"INSERT INTO Users (username, email, password, bio) VALUES (%s, %s, %s, %s)",
		(username, email, pwd_hash, bio or ""))
	conn.commit()
	cursor.close()
	conn.close()

	user = User()
	user.id = username
	flask_login.login_user(user)
	return render_template('hello.html', name=username, message='account created')


@app.route('/logout', methods=['POST'])
def logout():
	flask_login.logout_user()
	return redirect(url_for('home'))


def isUsernameUnique(username):
	# use this to check if a username has already been registered
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE username = %s", (username,))
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return len(rows) == 0


def isEmailUnique(email):
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute("SELECT email FROM Users WHERE email = %s", (email,))
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return len(rows) == 0


def getUserIdFromUsername(username):
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute("SELECT user_id FROM Users WHERE username = %s", (username,))
	row = cursor.fetchone()
	cursor.close()
	conn.close()
	return row[0] if row else None


def getCurrentUserId():
	if flask_login.current_user.is_authenticated:
		return getUserIdFromUsername(flask_login.current_user.id)
	return None

# end login code


# begin bracket creation code
@app.route('/create', methods=['GET', 'POST'])
@flask_login.login_required
def create_bracket():
	if request.method == 'POST':
		uid           = getUserIdFromUsername(flask_login.current_user.id)
		title         = request.form.get('title')
		description   = request.form.get('description', '')
		entrant_count = int(request.form.get('entrant_count'))
		deadline      = request.form.get('prediction_deadline') or None
		conn = get_conn()
		cursor = conn.cursor()
		try:
			# 1. insert the bracket row
			cursor.execute(
				"INSERT INTO Brackets (host_user_id, title, description, entrant_count, prediction_deadline) "
				"VALUES (%s, %s, %s, %s, %s)",
				(uid, title, description, entrant_count, deadline))
			cursor.execute("SELECT LAST_INSERT_ID()")
			bracket_id = cursor.fetchone()[0]

			# 2. insert all entrants in seed order
			entrant_ids = []
			for seed in range(1, entrant_count + 1):
				entrant_name = request.form.get('entrant_' + str(seed), '').strip()
				cursor.execute(
					"INSERT INTO Entrants (bracket_id, seed_number, name) VALUES (%s, %s, %s)",
					(bracket_id, seed, entrant_name))
				cursor.execute("SELECT LAST_INSERT_ID()")
				entrant_ids.append(cursor.fetchone()[0])

			# 3. create Round 1 matchups (seed pairs: 1v2, 3v4, ...)
			round_1_slots = entrant_count // 2
			for slot in range(1, round_1_slots + 1):
				a = entrant_ids[(slot - 1) * 2]
				b = entrant_ids[(slot - 1) * 2 + 1]
				cursor.execute(
					"INSERT INTO Matchups (bracket_id, round_number, slot_number, slot_a, slot_b) "
					"VALUES (%s, 1, %s, %s, %s)",
					(bracket_id, slot, a, b))

			# 4. create empty shells for later rounds
			slots = round_1_slots // 2
			round_num = 2
			while slots >= 1:
				for slot in range(1, slots + 1):
					cursor.execute(
						"INSERT INTO Matchups (bracket_id, round_number, slot_number) "
						"VALUES (%s, %s, %s)",
						(bracket_id, round_num, slot))
				slots //= 2
				round_num += 1

			conn.commit()
			cursor.close()
			conn.close()
			return redirect(url_for('view_bracket', bracket_id=bracket_id))
		except Exception as e:
			conn.rollback()
			cursor.close()
			conn.close()
			return render_template('create.html', error=str(e))
	else:
		return render_template('create.html')
# end bracket creation code


# begin browse code
def getAllBrackets():
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.status, b.entrant_count, b.created_at, u.username "
		"FROM Brackets b JOIN Users u ON b.host_user_id = u.user_id "
		"ORDER BY b.created_at DESC")
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return rows


@app.route('/browse', methods=['GET'])
def browse():
	brackets = getAllBrackets()
	return render_template('browse.html', brackets=brackets)
# end browse code


# begin bracket view code
def getBracketInfo(bracket_id):
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.description, b.status, b.entrant_count, u.username, "
		"       b.host_user_id, b.prediction_deadline "
		"FROM Brackets b JOIN Users u ON b.host_user_id = u.user_id "
		"WHERE b.bracket_id = %s", (bracket_id,))
	row = cursor.fetchone()
	cursor.close()
	conn.close()
	return row


def getMatchupsForBracket(bracket_id):
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id, m.round_number, m.slot_number, "
		"       ea.name, eb.name, ew.name, "
		"       m.vote_count_a, m.vote_count_b, "
		"       m.slot_a, m.slot_b, m.winner_id "
		"FROM Matchups m "
		"LEFT JOIN Entrants ea ON ea.entrant_id = m.slot_a "
		"LEFT JOIN Entrants eb ON eb.entrant_id = m.slot_b "
		"LEFT JOIN Entrants ew ON ew.entrant_id = m.winner_id "
		"WHERE m.bracket_id = %s "
		"ORDER BY m.round_number, m.slot_number", (bracket_id,))
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return rows


def getUserPredictions(user_id, bracket_id):
	if not user_id:
		return {}
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT p.matchup_id, p.picked_entrant_id "
		"FROM Predictions p "
		"JOIN Matchups m ON m.matchup_id = p.matchup_id "
		"WHERE p.user_id = %s AND m.bracket_id = %s",
		(user_id, bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return {r[0]: r[1] for r in rows}


def getUserVotes(user_id, bracket_id):
	if not user_id:
		return {}
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT v.matchup_id, v.entrant_id "
		"FROM Votes v "
		"JOIN Matchups m ON m.matchup_id = v.matchup_id "
		"WHERE v.user_id = %s AND m.bracket_id = %s",
		(user_id, bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	return {r[0]: r[1] for r in rows}


def getCommentsForBracket(bracket_id):
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT c.matchup_id, u.username, c.body, c.created_at "
		"FROM Comments c "
		"JOIN Users u ON u.user_id = c.user_id "
		"JOIN Matchups m ON m.matchup_id = c.matchup_id "
		"WHERE m.bracket_id = %s "
		"ORDER BY c.created_at ASC",
		(bracket_id,))
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	# return as dict: {matchup_id: [(username, body, created_at), ...]}
	result = {}
	for r in rows:
		result.setdefault(r[0], []).append((r[1], r[2], r[3]))
	return result


@app.route('/bracket<int:bracket_id>', methods=['GET'])
def view_bracket(bracket_id):
	bracket  = getBracketInfo(bracket_id)
	if not bracket:
		return "Bracket not found", 404
	matchups = getMatchupsForBracket(bracket_id)
	uid      = getCurrentUserId()
	user_predictions = getUserPredictions(uid, bracket_id)
	user_votes       = getUserVotes(uid, bracket_id)
	comments         = getCommentsForBracket(bracket_id)
	is_host = (uid == bracket[6]) if uid else False
	return render_template('bracket.html',
		bracket=bracket,
		matchups=matchups,
		user_predictions=user_predictions,
		user_votes=user_votes,
		comments=comments,
		is_host=is_host)
# end bracket view code


# default page
@app.route('/', methods=['GET', 'POST'])
def home():
	try:
		username = flask_login.current_user.id
		uid = getUserIdFromUsername(username)
		return render_template('hello.html', name=username, message='welcome to VERSUS', uid=uid)
	except AttributeError:
		return render_template('hello.html', message=None, uid=None)


# begin predictions code
@app.route('/bracket<int:bracket_id>/predict', methods=['POST'])
@flask_login.login_required
def submit_predictions(bracket_id):
	uid = getCurrentUserId()
	bracket = getBracketInfo(bracket_id)
	if not bracket or bracket[3] != 'predictions_open':
		return redirect(url_for('view_bracket', bracket_id=bracket_id))

	conn = get_conn()
	cursor = conn.cursor()
	try:
		now = datetime.datetime.now()
		# collect all picks from form: predict_<matchup_id> = entrant_id
		picks = {}
		for key, val in request.form.items():
			if key.startswith('predict_'):
				matchup_id = int(key.split('_')[1])
				picks[matchup_id] = int(val)

		for matchup_id, entrant_id in picks.items():
			# ON DUPLICATE KEY UPDATE lets a user revise their pick before deadline
			cursor.execute(
				"INSERT INTO Predictions (user_id, matchup_id, picked_entrant_id, submitted_at) "
				"VALUES (%s, %s, %s, %s) "
				"ON DUPLICATE KEY UPDATE picked_entrant_id = VALUES(picked_entrant_id), submitted_at = VALUES(submitted_at)",
				(uid, matchup_id, entrant_id, now))
		conn.commit()
	except mysql.connector.Error:
		conn.rollback()
	cursor.close()
	conn.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))
# end predictions code


# begin voting code
@app.route('/matchup<int:matchup_id>/vote', methods=['POST'])
@flask_login.login_required
def cast_vote(matchup_id):
	uid        = getCurrentUserId()
	entrant_id = int(request.form.get('entrant_id'))
	slot_side  = request.form.get('slot_side')  # 'a' or 'b'

	conn = get_conn()
	cursor = conn.cursor()
	try:
		# Insert vote — trigger checks bracket is in correct round
		cursor.execute(
			"INSERT INTO Votes (user_id, matchup_id, entrant_id) VALUES (%s, %s, %s)",
			(uid, matchup_id, entrant_id))
		# Atomic increment of the correct vote counter
		if slot_side == 'a':
			cursor.execute(
				"UPDATE Matchups SET vote_count_a = vote_count_a + 1 WHERE matchup_id = %s",
				(matchup_id,))
		else:
			cursor.execute(
				"UPDATE Matchups SET vote_count_b = vote_count_b + 1 WHERE matchup_id = %s",
				(matchup_id,))
		conn.commit()
	except mysql.connector.Error:
		conn.rollback()
	cursor.close()
	conn.close()

	# redirect back to the bracket
	conn2 = get_conn()
	cur2  = conn2.cursor()
	cur2.execute("SELECT bracket_id FROM Matchups WHERE matchup_id = %s", (matchup_id,))
	row = cur2.fetchone()
	cur2.close()
	conn2.close()
	bracket_id = row[0] if row else 1
	return redirect(url_for('view_bracket', bracket_id=bracket_id))
# end voting code


# begin bracket status code
@app.route('/bracket<int:bracket_id>/open_predictions', methods=['POST'])
@flask_login.login_required
def open_predictions(bracket_id):
	uid = getCurrentUserId()
	bracket = getBracketInfo(bracket_id)
	if not bracket or bracket[6] != uid:
		return redirect(url_for('view_bracket', bracket_id=bracket_id))
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"UPDATE Brackets SET status = 'predictions_open' WHERE bracket_id = %s AND status = 'draft'",
		(bracket_id,))
	conn.commit()
	cursor.close()
	conn.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))


@app.route('/bracket<int:bracket_id>/start_round', methods=['POST'])
@flask_login.login_required
def start_round(bracket_id):
	uid = getCurrentUserId()
	bracket = getBracketInfo(bracket_id)
	if not bracket or bracket[6] != uid:
		return redirect(url_for('view_bracket', bracket_id=bracket_id))
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"UPDATE Brackets SET status = 'round_1' WHERE bracket_id = %s AND status = 'predictions_open'",
		(bracket_id,))
	conn.commit()
	cursor.close()
	conn.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))


@app.route('/bracket<int:bracket_id>/close_round', methods=['POST'])
@flask_login.login_required
def close_round(bracket_id):
	uid = getCurrentUserId()
	bracket = getBracketInfo(bracket_id)
	if not bracket or bracket[6] != uid:
		return redirect(url_for('view_bracket', bracket_id=bracket_id))

	status = bracket[3]
	if not status.startswith('round_'):
		return redirect(url_for('view_bracket', bracket_id=bracket_id))

	round_num = int(status.split('_')[1])
	conn = get_conn()
	cursor = conn.cursor()
	try:
		cursor.callproc('close_round', (bracket_id, round_num))
		conn.commit()
	except Exception:
		conn.rollback()
	cursor.close()
	conn.close()
	return redirect(url_for('view_bracket', bracket_id=bracket_id))
# end bracket status code


# begin leaderboard code
@app.route('/leaderboard', methods=['GET'])
def leaderboard():
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"SELECT user_id, username, total_points, rank_position, dense_rank_position, percentile "
		"FROM Leaderboard ORDER BY rank_position")
	rows = cursor.fetchall()
	cursor.close()
	conn.close()
	uid = getCurrentUserId()
	return render_template('leaderboard.html', rows=rows, current_uid=uid)
# end leaderboard code


# begin champion path code
@app.route('/bracket<int:bracket_id>/champion', methods=['GET'])
def champion_path(bracket_id):
	bracket = getBracketInfo(bracket_id)
	if not bracket or bracket[3] != 'completed':
		return redirect(url_for('view_bracket', bracket_id=bracket_id))

	conn = get_conn()
	cursor = conn.cursor()
	# Recursive CTE: find the final matchup winner, then walk backwards
	cursor.execute("""
		WITH RECURSIVE champion_walk AS (
			SELECT
				m.matchup_id,
				m.round_number,
				m.slot_number,
				m.winner_id,
				m.slot_a,
				m.slot_b,
				m.vote_count_a,
				m.vote_count_b,
				ea.name AS entrant_a_name,
				eb.name AS entrant_b_name,
				ew.name AS winner_name
			FROM Matchups m
			LEFT JOIN Entrants ea ON ea.entrant_id = m.slot_a
			LEFT JOIN Entrants eb ON eb.entrant_id = m.slot_b
			LEFT JOIN Entrants ew ON ew.entrant_id = m.winner_id
			WHERE m.bracket_id = %s
			  AND m.round_number = (
				  SELECT MAX(round_number) FROM Matchups WHERE bracket_id = %s
			  )
			  AND m.slot_number = 1

			UNION ALL
			SELECT
				m.matchup_id,
				m.round_number,
				m.slot_number,
				m.winner_id,
				m.slot_a,
				m.slot_b,
				m.vote_count_a,
				m.vote_count_b,
				ea.name,
				eb.name,
				ew.name
			FROM Matchups m
			JOIN champion_walk cw
			  ON m.bracket_id = %s
			 AND m.round_number = cw.round_number - 1
			 AND (m.winner_id = cw.slot_a OR m.winner_id = cw.slot_b)
			LEFT JOIN Entrants ea ON ea.entrant_id = m.slot_a
			LEFT JOIN Entrants eb ON eb.entrant_id = m.slot_b
			LEFT JOIN Entrants ew ON ew.entrant_id = m.winner_id
		)
		SELECT * FROM champion_walk ORDER BY round_number
	""", (bracket_id, bracket_id, bracket_id))
	path = cursor.fetchall()
	cursor.close()
	conn.close()
	return render_template('champion.html', bracket=bracket, path=path)
# end champion path code


# begin comments code
@app.route('/matchup<int:matchup_id>/comment', methods=['POST'])
@flask_login.login_required
def post_comment(matchup_id):
	uid  = getCurrentUserId()
	body = request.form.get('body', '').strip()
	if body:
		conn = get_conn()
		cursor = conn.cursor()
		cursor.execute(
			"INSERT INTO Comments (user_id, matchup_id, body) VALUES (%s, %s, %s)",
			(uid, matchup_id, body))
		conn.commit()
		cursor.close()
		conn.close()
	# redirect back to bracket
	conn2 = get_conn()
	cur2  = conn2.cursor()
	cur2.execute("SELECT bracket_id FROM Matchups WHERE matchup_id = %s", (matchup_id,))
	row = cur2.fetchone()
	cur2.close()
	conn2.close()
	bracket_id = row[0] if row else 1
	return redirect(url_for('view_bracket', bracket_id=bracket_id))
# end comments code


# begin follows code
@app.route('/user/<int:target_uid>/follow', methods=['POST'])
@flask_login.login_required
def follow_user(target_uid):
	uid = getCurrentUserId()
	if uid == target_uid:
		return redirect(url_for('profile', user_id=target_uid))
	conn = get_conn()
	cursor = conn.cursor()
	try:
		cursor.execute(
			"INSERT IGNORE INTO Follows (follower_id, followed_id) VALUES (%s, %s)",
			(uid, target_uid))
		conn.commit()
	except:
		conn.rollback()
	cursor.close()
	conn.close()
	return redirect(url_for('profile', user_id=target_uid))


@app.route('/user/<int:target_uid>/unfollow', methods=['POST'])
@flask_login.login_required
def unfollow_user(target_uid):
	uid = getCurrentUserId()
	conn = get_conn()
	cursor = conn.cursor()
	cursor.execute(
		"DELETE FROM Follows WHERE follower_id = %s AND followed_id = %s",
		(uid, target_uid))
	conn.commit()
	cursor.close()
	conn.close()
	return redirect(url_for('profile', user_id=target_uid))
# end follows code


# begin profile code
@app.route('/user/<int:user_id>', methods=['GET'])
def profile(user_id):
	conn = get_conn()
	cursor = conn.cursor()

	# Basic user info
	cursor.execute(
		"SELECT user_id, username, email, bio, join_date "
		"FROM Users WHERE user_id = %s", (user_id,))
	user_row = cursor.fetchone()
	if not user_row:
		cursor.close()
		conn.close()
		return "User not found", 404

	# Prediction stats
	cursor.execute(
		"SELECT COUNT(*), "
		"       SUM(CASE WHEN prediction_result = 1 THEN 1 ELSE 0 END), "
		"       COALESCE(SUM(points_earned), 0) "
		"FROM Predictions WHERE user_id = %s", (user_id,))
	pred_stats = cursor.fetchone()

	# Brackets hosted
	cursor.execute(
		"SELECT bracket_id, title, status, entrant_count, created_at "
		"FROM Brackets WHERE host_user_id = %s ORDER BY created_at DESC",
		(user_id,))
	hosted = cursor.fetchall()

	# Achievements
	cursor.execute(
		"SELECT a.name, a.description, ac.earned_at "
		"FROM Achieved ac JOIN Achievements a ON a.code = ac.achievement_code "
		"WHERE ac.user_id = %s", (user_id,))
	achievements = cursor.fetchall()

	# Followers
	cursor.execute(
		"SELECT u.user_id, u.username FROM Follows f "
		"JOIN Users u ON u.user_id = f.follower_id "
		"WHERE f.followed_id = %s", (user_id,))
	followers = cursor.fetchall()

	# Following
	cursor.execute(
		"SELECT u.user_id, u.username FROM Follows f "
		"JOIN Users u ON u.user_id = f.followed_id "
		"WHERE f.follower_id = %s", (user_id,))
	following = cursor.fetchall()

	cursor.close()
	conn.close()

	uid = getCurrentUserId()
	# Check if current user follows this profile
	is_following = False
	if uid and uid != user_id:
		conn2 = get_conn()
		cur2  = conn2.cursor()
		cur2.execute(
			"SELECT 1 FROM Follows WHERE follower_id = %s AND followed_id = %s",
			(uid, user_id))
		is_following = bool(cur2.fetchone())
		cur2.close()
		conn2.close()

	return render_template('profile.html',
		user=user_row,
		pred_stats=pred_stats,
		hosted=hosted,
		achievements=achievements,
		followers=followers,
		following=following,
		is_following=is_following,
		current_uid=uid)
# end profile code


# begin admin code
@app.route('/admin', methods=['GET', 'POST'])
@flask_login.login_required
def admin_console():
	if flask_login.current_user.id != 'admin':
		return render_template('unauth.html')

	result = None
	error  = None
	query  = ''
	if request.method == 'POST':
		query  = request.form.get('query', '').strip()
		conn   = get_conn()
		cursor = conn.cursor()
		try:
			cursor.execute(query)
			if cursor.description:
				cols   = [d[0] for d in cursor.description]
				rows   = cursor.fetchall()
				result = {'cols': cols, 'rows': rows}
			else:
				conn.commit()
				result = {'cols': ['rows_affected'], 'rows': [(cursor.rowcount,)]}
		except Exception as e:
			error = str(e)
		finally:
			cursor.close()
			conn.close()

	return render_template('admin.html', query=query, result=result, error=error)
# end admin code


if __name__ == "__main__":
	# this is invoked when in the shell you run
	# $ python app.py
	app.debug = True
	app.run(port=5001, debug=True)
