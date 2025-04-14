##############################
##### PCAN Configuration #####
##############################
# Basic configuration
FL = 0
FR = 1
RL = 2
RR = 3

MAX_ERROR_COUNT     = 5
CONFIRM_OFF_COUNT   = 10
BITRATE             = "f_clock_mhz=40,nom_brp=1,nom_tseg1=63,nom_tseg2=16,nom_sjw=16,data_brp=2,data_tseg1=14,data_tseg2=5,data_sjw=4"
DEV_ID_LIST         = ["0", "1", "2"]
RECV_MSG_ID_LIST    = {0x1FF100A2: "FL", 0x1FF100A3: "FR", 0x1FF100A4: "RL", 0x1FF100A5: "RR"}

TX_POWER_LIMIT      = [10, 14]
TEMP_LIMIT          = [-40, 125]

# Door test message preset
DOOR_MSG_ID_LIST    = {"1E1": "FL", "1E2": "FR", "1E3": "RL", "1E4": "RR"}
DOOR_DLC            = 16
DOOR_ACT            = ["10", ["00", "00", "00", "00", "00", "01", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00"]]
DOOR_DEACT          = ["10", ["00", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00", "00"]]
DOOR_FL_MSG_ID      = ["1E1", "1FF1A200", "1FF100A2"]
DOOR_FR_MSG_ID      = ["1E2", "1FF1A300", "1FF100A3"]
DOOR_RL_MSG_ID      = ["1E3", "1FF1A400", "1FF100A4"]
DOOR_RR_MSG_ID      = ["1E4", "1FF1A500", "1FF100A5"]
DOOR_RCV_MSG_ID_FL  = ["0x543", "1234", "12345"]
DOOR_RCV_MSG_ID_FR  = ["0x123", "1234", "12345"]
DOOR_RCV_MSG_ID_RL  = ["0x123", "1234", "12345"]
DOOR_RCV_MSG_ID_RR  = ["0x123", "1234", "12345"]

# Talegate test message preset
TALEGATE_MSG_ID     = ["18060501", "1FF01400"]
TALEGATE_DLC        = 8
TALEGATE_ACT        = ["00", "00", "00", "00", "00", "01", "00", "00"]
TALEGATE_DEACT      = ["00", "00", "00", "00", "00", "00", "00", "00"]
TALEGATE_RCV_MSG_ID = ["0x547", "0x17c5f801", "0x17FC0014", "0x1FF11400"]

# Common message preset
RQST_PWR_TEMP       = ["30", "05", "00", "55", "55", "55", "55", "55"]
RQST_PWR_TEMP_PRE1  = ["03", "0C", "02", "04", "55", "55", "55", "55"]
RQST_PWR_TEMP_PRE2  = ["03", "0E", "02", "01", "55", "55", "55", "55"]
RQST_PWR_TEMP_PRE3  = ["03", "15", "02", "01", "55", "55", "55", "55"]

# = ["03", "12", "06", "01", "55", "55", "55", "55"]
# FL's recive MSG_ID → 
# FR's recive MSG_ID → 
# RL's recive MSG_ID → 
# RR's recive MSG_ID → 
# Talegate's recive MSG_ID → '0x547', '0x17C5F801', '0x17FC0014', '1FF11400(Temperature)'