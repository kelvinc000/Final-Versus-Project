
DROP DATABASE IF EXISTS versus;
CREATE DATABASE versus;
USE versus;

CREATE TABLE Users (
    user_id        INT AUTO_INCREMENT,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password       VARCHAR(255) NOT NULL,
    bio            TEXT,
    join_date      DATE DEFAULT (CURRENT_DATE),
    PRIMARY KEY (user_id)
);

CREATE TABLE Brackets (
    bracket_id          INT AUTO_INCREMENT,
    host_user_id        INT         NOT NULL,
    title               VARCHAR(200) NOT NULL,
    description         TEXT,
    entrant_count       INT         NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'draft',
    prediction_deadline DATE,
    created_at          DATE DEFAULT (CURRENT_DATE),
    PRIMARY KEY (bracket_id),
    FOREIGN KEY (host_user_id) REFERENCES Users(user_id),
    CHECK (entrant_count IN (4, 8, 16, 32)),
    CHECK (status IN ('draft', 'predictions_open',
        'round_1', 'round_2', 'round_3', 'round_4', 'round_5', 'completed'))
);

CREATE TABLE Entrants (
    entrant_id   INT AUTO_INCREMENT,
    bracket_id   INT          NOT NULL,
    seed_number  INT          NOT NULL,
    name         VARCHAR(200) NOT NULL,
    PRIMARY KEY (entrant_id),
    FOREIGN KEY (bracket_id) REFERENCES Brackets(bracket_id) ON DELETE CASCADE,
    UNIQUE (bracket_id, seed_number)
);

CREATE TABLE Matchups (
    matchup_id   INT AUTO_INCREMENT,
    bracket_id   INT NOT NULL,
    round_number INT NOT NULL,
    slot_number  INT NOT NULL,
    slot_a       INT,
    slot_b       INT,
    winner_id    INT,
    vote_count_a INT DEFAULT 0,
    vote_count_b INT DEFAULT 0,
    PRIMARY KEY (matchup_id),
    FOREIGN KEY (bracket_id) REFERENCES Brackets(bracket_id) ON DELETE CASCADE,
    FOREIGN KEY (slot_a)     REFERENCES Entrants(entrant_id),
    FOREIGN KEY (slot_b)     REFERENCES Entrants(entrant_id),
    FOREIGN KEY (winner_id)  REFERENCES Entrants(entrant_id),
    UNIQUE (bracket_id, round_number, slot_number)
);

CREATE TABLE Predictions (
    prediction_id     INT AUTO_INCREMENT,
    user_id           INT      NOT NULL,
    matchup_id        INT      NOT NULL,
    picked_entrant_id INT      NOT NULL,
    prediction_result BOOLEAN,
    points_earned     INT      DEFAULT 0,
    submitted_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (prediction_id),
    FOREIGN KEY (user_id)           REFERENCES Users(user_id),
    FOREIGN KEY (matchup_id)        REFERENCES Matchups(matchup_id) ON DELETE CASCADE,
    FOREIGN KEY (picked_entrant_id) REFERENCES Entrants(entrant_id),
    UNIQUE (user_id, matchup_id)
);

CREATE TABLE Votes (
    vote_id    INT AUTO_INCREMENT,
    user_id    INT      NOT NULL,
    matchup_id INT      NOT NULL,
    entrant_id INT      NOT NULL,
    voted_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (vote_id),
    FOREIGN KEY (user_id)    REFERENCES Users(user_id),
    FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id) ON DELETE CASCADE,
    FOREIGN KEY (entrant_id) REFERENCES Entrants(entrant_id),
    UNIQUE (user_id, matchup_id)
);

CREATE TABLE Achievements (
    code        VARCHAR(50),
    name        VARCHAR(100) NOT NULL,
    description TEXT         NOT NULL,
    PRIMARY KEY (code)
);

CREATE TABLE Achieved (
    user_id          INT         NOT NULL,
    achievement_code VARCHAR(50) NOT NULL,
    earned_at        DATE DEFAULT (CURRENT_DATE),
    PRIMARY KEY (user_id, achievement_code),
    FOREIGN KEY (user_id)          REFERENCES Users(user_id),
    FOREIGN KEY (achievement_code) REFERENCES Achievements(code)
);

CREATE TABLE Follows (
    follower_id INT  NOT NULL,
    followed_id INT  NOT NULL,
    followed_at DATE DEFAULT (CURRENT_DATE),
    PRIMARY KEY (follower_id, followed_id),
    FOREIGN KEY (follower_id) REFERENCES Users(user_id),
    FOREIGN KEY (followed_id) REFERENCES Users(user_id),
    CHECK (follower_id <> followed_id)
);

CREATE TABLE Comments (
    comment_id INT AUTO_INCREMENT,
    user_id    INT      NOT NULL,
    matchup_id INT      NOT NULL,
    body       TEXT     NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (comment_id),
    FOREIGN KEY (user_id)    REFERENCES Users(user_id),
    FOREIGN KEY (matchup_id) REFERENCES Matchups(matchup_id) ON DELETE CASCADE
);

DELIMITER //

CREATE TRIGGER predictionWindowCheck
BEFORE INSERT ON Predictions
FOR EACH ROW
BEGIN
    DECLARE bracketStatus VARCHAR(20);
    SELECT B.status INTO bracketStatus
    FROM Matchups M
    JOIN Brackets B ON M.bracket_id = B.bracket_id
    WHERE M.matchup_id = NEW.matchup_id;

    IF bracketStatus <> 'predictions_open' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Predictions can only be submitted while the bracket is predictions_open';
    END IF;
END//

CREATE TRIGGER voteRoundCheck
BEFORE INSERT ON Votes
FOR EACH ROW
BEGIN
    DECLARE bracketStatus VARCHAR(20);
    DECLARE matchupRound  INT;
    SELECT B.status, M.round_number INTO bracketStatus, matchupRound
    FROM Matchups M
    JOIN Brackets B ON M.bracket_id = B.bracket_id
    WHERE M.matchup_id = NEW.matchup_id;

    IF bracketStatus <> CONCAT('round_', matchupRound) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Votes can only be cast on matchups in the bracket current round';
    END IF;
END//
CREATE TRIGGER trg_award_bracket_maker
AFTER INSERT ON Brackets
FOR EACH ROW
BEGIN
    DECLARE bracket_total INT;
    SELECT COUNT(*) INTO bracket_total
    FROM Brackets
    WHERE host_user_id = NEW.host_user_id;

    IF bracket_total = 1 THEN
        INSERT IGNORE INTO Achieved (user_id, achievement_code)
        VALUES (NEW.host_user_id, 'bracket_maker');
    END IF;
END//

CREATE TRIGGER trg_award_locked_in
AFTER INSERT ON Predictions
FOR EACH ROW
BEGIN
    DECLARE prediction_total INT;
    SELECT COUNT(*) INTO prediction_total
    FROM Predictions
    WHERE user_id = NEW.user_id;

    IF prediction_total = 10 THEN
        INSERT IGNORE INTO Achieved (user_id, achievement_code)
        VALUES (NEW.user_id, 'locked_in');
    END IF;
END//

DELIMITER ;

DELIMITER //

CREATE PROCEDURE close_round(IN p_bracket_id INT, IN p_round INT)
close_round_block: BEGIN
    DECLARE v_entrant_count    INT;
    DECLARE v_total_rounds     INT;
    DECLARE v_is_final         BOOLEAN DEFAULT FALSE;
    DECLARE done               INT     DEFAULT FALSE;
    DECLARE v_matchup_id       INT;
    DECLARE v_slot_a           INT;
    DECLARE v_slot_b           INT;
    DECLARE v_votes_a          INT;
    DECLARE v_votes_b          INT;
    DECLARE v_winner           INT;
    DECLARE v_slot_number      INT;
    DECLARE v_next_round       INT;
    DECLARE v_next_slot_number INT;
    DECLARE v_next_matchup_id  INT;
    DECLARE v_is_first_in_pair INT;

    DECLARE matchup_cursor CURSOR FOR
        SELECT matchup_id, slot_a, slot_b, vote_count_a, vote_count_b, slot_number
        FROM Matchups
        WHERE bracket_id = p_bracket_id AND round_number = p_round;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    SELECT entrant_count INTO v_entrant_count
    FROM Brackets WHERE bracket_id = p_bracket_id;

    IF v_entrant_count IS NULL THEN
        LEAVE close_round_block;
    END IF;

    SET v_total_rounds = LOG2(v_entrant_count);   
    IF p_round = v_total_rounds THEN
        SET v_is_final = TRUE;
    END IF;
    SET v_next_round = p_round + 1;

    -- Task 1 + Task 3: pick winners and promote them
    OPEN matchup_cursor;
    read_loop: LOOP
        FETCH matchup_cursor
            INTO v_matchup_id, v_slot_a, v_slot_b, v_votes_a, v_votes_b, v_slot_number;
        IF done THEN LEAVE read_loop; END IF;
        IF v_votes_a >= v_votes_b THEN
            SET v_winner = v_slot_a;
        ELSE
            SET v_winner = v_slot_b;
        END IF;

        UPDATE Matchups SET winner_id = v_winner WHERE matchup_id = v_matchup_id;

        IF NOT v_is_final THEN
            SET v_next_slot_number = CEIL(v_slot_number / 2);
            SET v_is_first_in_pair = MOD(v_slot_number, 2);

            SELECT matchup_id INTO v_next_matchup_id
            FROM Matchups
            WHERE bracket_id   = p_bracket_id
              AND round_number  = v_next_round
              AND slot_number   = v_next_slot_number;

            IF v_is_first_in_pair = 1 THEN
                UPDATE Matchups SET slot_a = v_winner WHERE matchup_id = v_next_matchup_id;
            ELSE
                UPDATE Matchups SET slot_b = v_winner WHERE matchup_id = v_next_matchup_id;
            END IF;
        END IF;
    END LOOP;
    CLOSE matchup_cursor;

    -- Task 2: score predictions 
    UPDATE Predictions p
    JOIN   Matchups    m ON m.matchup_id = p.matchup_id
    SET    p.prediction_result = (p.picked_entrant_id = m.winner_id),
           p.points_earned     = IF(p.picked_entrant_id = m.winner_id, 1, 0)
    WHERE  m.bracket_id  = p_bracket_id
      AND  m.round_number = p_round;

    -- Task 4: advance bracket status
    IF v_is_final THEN
        UPDATE Brackets SET status = 'completed'
        WHERE bracket_id = p_bracket_id;
    ELSE
        UPDATE Brackets SET status = CONCAT('round_', v_next_round)
        WHERE bracket_id = p_bracket_id;
    END IF;
END close_round_block//

DELIMITER ;
CREATE VIEW Leaderboard AS
SELECT
    u.user_id,
    u.username,
    COALESCE(SUM(p.points_earned), 0)                                          AS total_points,
    RANK()         OVER (ORDER BY COALESCE(SUM(p.points_earned), 0) DESC)      AS rank_position,
    DENSE_RANK()   OVER (ORDER BY COALESCE(SUM(p.points_earned), 0) DESC)      AS dense_rank_position,
    PERCENT_RANK() OVER (ORDER BY COALESCE(SUM(p.points_earned), 0) DESC)      AS percentile
FROM   Users u
LEFT JOIN Predictions p ON p.user_id = u.user_id
GROUP  BY u.user_id, u.username;
INSERT INTO Achievements (code, name, description) VALUES
    ('bracket_maker', 'Bracket Maker', 'Hosted your first bracket'),
    ('locked_in',     'Locked In',     'Submitted your 10th prediction');
