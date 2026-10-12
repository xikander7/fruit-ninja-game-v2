// Screen Elements
const startupScreen = document.getElementById("startup-screen");
const menuScreen = document.getElementById("menu-screen");
const gameScreen = document.getElementById("game-screen");
const gameoverScreen = document.getElementById("gameover-screen");

const startBtn = document.getElementById("start-btn");
const restartBtn = document.getElementById("restart-btn");
const menuBackBtn = document.getElementById("menu-back-btn");
const modeBtns = document.querySelectorAll(".mode-btn");

const canvas = document.getElementById("gameCanvas");
const ctx = canvas.getContext("2d");

const scoreEl = document.getElementById("score");
const levelEl = document.getElementById("level");
const livesEl = document.getElementById("lives");
const finalScoreEl = document.getElementById("final-score");
const finalLevelEl = document.getElementById("final-level");
const highScoreListEl = document.getElementById("high-score-list");

// Game Variables
let gameMode = "classic";
let score = 0;
let level = 1;
let lives = 3;
let gameRunning = false;
let fruits = [];
let slicedHalves = [];
let sliceTrail = [];

// High Scores stored in browser LocalStorage
let highScores = JSON.parse(localStorage.getItem('fruitNinjaHighScores')) || [];

// Audio Context for Realistic Slash / Bomb Sound Effects
const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

function playSlashSound() {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    
    // Generate white noise "whoosh" sound for blade cutting
    const bufferSize = audioCtx.sampleRate * 0.12; 
    const buffer = audioCtx.createBuffer(1, bufferSize, audioCtx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
        data[i] = Math.random() * 2 - 1;
    }

    const noise = audioCtx.createBufferSource();
    noise.buffer = buffer;

    const filter = audioCtx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.setValueAtTime(1400, audioCtx.currentTime);
    filter.frequency.exponentialRampToValueAtTime(300, audioCtx.currentTime + 0.12);
    filter.Q.value = 4;

    const gain = audioCtx.createGain();
    gain.gain.setValueAtTime(0.5, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.12);

    noise.connect(filter);
    filter.connect(gain);
    gain.connect(audioCtx.destination);

    noise.start();
}

function playBombSound() {
    if (audioCtx.state === 'suspended') audioCtx.resume();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'square';
    osc.frequency.setValueAtTime(150, audioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(30, audioCtx.currentTime + 0.4);
    gain.gain.setValueAtTime(0.4, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.4);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.4);
}

// Navigation Events
startBtn.addEventListener("click", () => {
    startupScreen.classList.add("hidden");
    menuScreen.classList.remove("hidden");
});

modeBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
        gameMode = e.currentTarget.getAttribute("data-mode");
        menuScreen.classList.add("hidden");
        gameScreen.classList.remove("hidden");
        startGame();
    });
});

restartBtn.addEventListener("click", () => {
    gameoverScreen.classList.add("hidden");
    gameScreen.classList.remove("hidden");
    startGame();
});

menuBackBtn.addEventListener("click", () => {
    gameoverScreen.classList.add("hidden");
    menuScreen.classList.remove("hidden");
});

function startGame() {
    score = 0;
    level = 1;
    lives = gameMode === 'zen' ? 999 : 3;
    fruits = [];
    slicedHalves = [];
    gameRunning = true;
    updateHUD();
    gameLoop();
}

function updateHUD() {
    scoreEl.textContent = score;
    levelEl.textContent = level;
    if (gameMode === 'zen') {
        livesEl.textContent = " Zen Mode";
    } else {
        livesEl.textContent = "❤️".repeat(Math.max(0, lives));
    }
}

// Fruit Class
class Fruit {
    constructor() {
        this.x = Math.random() * (canvas.width - 250) + 120;
        this.y = canvas.height + 50;
        this.radius = 32;
        this.dx = (Math.random() - 0.5) * (4 + level);
        this.dy = -(Math.random() * 4 + 12 + (level * 0.4));
        this.gravity = 0.35;
        this.active = true;
        
        this.isBomb = (gameMode !== 'zen' && Math.random() < 0.18);
        const fruitColors = ["#ff3b30", "#4cd964", "#ffcc00", "#ff9500", "#ff2d55"];
        this.color = this.isBomb ? "#222" : fruitColors[Math.floor(Math.random() * fruitColors.length)];
    }

    update() {
        this.x += this.dx;
        this.y += this.dy;
        this.dy += this.gravity;
    }

    draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.fillStyle = this.color;
        ctx.fill();
        ctx.lineWidth = 3;
        ctx.strokeStyle = this.isBomb ? "#ff3b30" : "#ffffff";
        ctx.stroke();
        ctx.closePath();

        ctx.font = "22px Arial";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(this.isBomb ? "💣" : "🍎", this.x, this.y);
    }
}

// Sliced Fruit Halves Class (Creates the proper cutting effect)
class HalfFruit {
    constructor(x, y, color, side) {
        this.x = x;
        this.y = y;
        this.color = color;
        this.side = side; // 'left' or 'right'
        this.dx = side === 'left' ? -4.5 : 4.5;
        this.dy = -3;
        this.gravity = 0.45;
        this.rotation = 0;
        this.dRot = side === 'left' ? -0.12 : 0.12;
    }

    update() {
        this.x += this.dx;
        this.y += this.dy;
        this.dy += this.gravity;
        this.rotation += this.dRot;
    }

    draw() {
        ctx.save();
        ctx.translate(this.x, this.y);
        ctx.rotate(this.rotation);
        ctx.beginPath();
        if (this.side === 'left') {
            ctx.arc(0, 0, 32, Math.PI / 2, Math.PI * 1.5);
        } else {
            ctx.arc(0, 0, 32, Math.PI * 1.5, Math.PI / 2);
        }
        ctx.fillStyle = this.color;
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#ffffff';
        ctx.stroke();
        ctx.closePath();
        ctx.restore();
    }
}

// Mouse Slicing & Collision Detection
canvas.addEventListener("mousemove", (e) => {
    if (!gameRunning) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    sliceTrail.push({ x: mouseX, y: mouseY, alpha: 1 });
    if (sliceTrail.length > 12) sliceTrail.shift();

    fruits.forEach(fruit => {
        if (!fruit.active) return;
        const dist = Math.hypot(mouseX - fruit.x, mouseY - fruit.y);
        if (dist < fruit.radius) {
            fruit.active = false;
            
            if (fruit.isBomb) {
                playBombSound();
                lives -= 2;
                if (lives <= 0) gameOver();
            } else {
                playSlashSound(); // Realistic blade slash audio
                score += 10 * level;
                level = Math.floor(score / 120) + 1;
                
                // Spawn two cut halves flying apart!
                slicedHalves.push(new HalfFruit(fruit.x, fruit.y, fruit.color, 'left'));
                slicedHalves.push(new HalfFruit(fruit.x, fruit.y, fruit.color, 'right'));
            }
            updateHUD();
        }
    });
});

function gameOver() {
    gameRunning = false;
    
    // Save high score
    if (score > 0) {
        highScores.push(score);
        highScores.sort((a, b) => b - a);
        highScores = highScores.slice(0, 5); // Keep top 5 scores
        localStorage.setItem('fruitNinjaHighScores', JSON.stringify(highScores));
    }

    // Render high score board list
    highScoreListEl.innerHTML = highScores.length > 0 
        ? highScores.map((s, index) => `<li>#${index + 1}: ${s} pts</li>`).join('') 
        : '<li>No scores yet</li>';

    gameScreen.classList.add("hidden");
    gameoverScreen.classList.remove("hidden");
    finalScoreEl.textContent = score;
    finalLevelEl.textContent = level;
}

let spawnTimer = 0;
function gameLoop() {
    if (!gameRunning) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Spawn fruits
    spawnTimer++;
    if (spawnTimer > Math.max(25, 75 - (level * 7))) {
        fruits.push(new Fruit());
        if (level >= 2 && Math.random() > 0.4) {
            fruits.push(new Fruit());
        }
        spawnTimer = 0;
    }

    // Update & draw whole fruits
    fruits.forEach(fruit => {
        fruit.update();
        fruit.draw();

        if (fruit.y > canvas.height + 60 && fruit.active) {
            fruit.active = false;
            if (!fruit.isBomb && gameMode === 'classic') {
                lives--;
                updateHUD();
                if (lives <= 0) gameOver();
            }
        }
    });

    // Update & draw sliced fruit halves
    slicedHalves.forEach(half => {
        half.update();
        half.draw();
    });

    // Clean up dead objects
    fruits = fruits.filter(f => f.y < canvas.height + 100);
    slicedHalves = slicedHalves.filter(h => h.y < canvas.height + 100);

    // Draw Blue Glowing Blade Trail
    if (sliceTrail.length > 1) {
        ctx.beginPath();
        ctx.moveTo(sliceTrail[0].x, sliceTrail[0].y);
        for (let i = 1; i < sliceTrail.length; i++) {
            ctx.lineTo(sliceTrail[i].x, sliceTrail[i].y);
        }
        ctx.strokeStyle = "rgba(0, 240, 255, 0.85)";
        ctx.lineWidth = 5;
        ctx.lineCap = "round";
        ctx.stroke();
        ctx.closePath();

        sliceTrail.forEach(p => p.alpha -= 0.1);
        sliceTrail = sliceTrail.filter(p => p.alpha > 0);
    }

    requestAnimationFrame(gameLoop);
}