# Arena — Two-Player Real-Time Multiplayer Fighting Game  
A local client–server based real-time action game implemented in Python for My IB Computer Science Internal Assessment.  
Players select heroes, move freely, cast skills, and attempt to reduce the opponent’s HP to zero.

---
## 🚀 Features

### 🎮 Gameplay
- Real-time movement (↑ ↓ ← →)
- Three skills per hero (keys 1/2/3)
- Dynamic damage calculation using a configurable algorithm
- HP bar display above each character
- Game-over screen when a player dies
- Visual skill effects (triangles / circles / rectangles)

### 👥 Multiplayer System
- Two-player synchronous gameplay  
- Local socket-based communication  
- Full-duplex message transfer  
- Movement, skill, and health updates are transmitted in real time  
- Client auto-connect with retry UI

### 🖼 Graphics & UI
- Tkinter GUI  
- Sprite support (PNG images loaded via Pillow)  
- Welcome screen + “How to Play” instructions  
- Hero selection menu  
- Clean battlefield UI with center line and decorations

### 🧩 Hero System
- Heroes are loaded from an external JSON file (`property.json`)  
- Each hero has:
  - `base_health`
  - `physical_attack`
  - `skills` (damage + multiplier)
- New heroes can be added simply by editing the JSON file and adding a sprite

## 📁 Project Structure
```text
.
├── server_run.py        # Game server logic
├── clientC.py           # Game client with GUI
├── property.json        # Hero definitions
├── assets/              # Sprite images (64×64 PNG)
│   ├── zhaoyun.png
│   ├── lubanqihao.png
│   └── ...
└── README.md
```


## How to Run the system:
  python server_run.py
  
    Server started on 127.0.0.1:1212, waiting for connections...
    
  python clientC.py
  
    Start Client 1
    
  python clientC.py
  
    Start Client 2
    
  
## How to Add another hero:
  To add another hero:
  
    1. Copy an existing hero block
    
    2. Change name / stats / skills
    
    3. Add a sprite:
    
      assets/<hero_name>.png
      
        filename lowercase
        
        size 64×64 recommended
        
    The game loads heroes automatically — no code modification needed.
    

## 🌱 Future Enhancements

The system is designed to be expandable:

- Online multiplayer (rooms, matchmaking)
- Real hero animations (GIF spritesheets)
- More skill types (AOE, projectile, dash)
- Character selection by both players simultaneously
- Enhanced UI with CustomTkinter
- Game replays / recording
- Multi-team modes (2v2, 3v3)

## 🛠 Troubleshooting
  “Cannot connect to server”
    Ensure server is running
    
    Check port 1212 is open locally
    
    Retry via dialog window
    

  Sprites not showing
    Make sure sprite name matches hero name exactly
    
    Must be PNG
    
    Must be placed in /assets
    

  JSONDecodeError
    Caused by partial packet
    
    Automatically handled by buffer logic
    
