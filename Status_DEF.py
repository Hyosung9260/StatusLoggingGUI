##############################
##### PCAN Configuration #####
##############################
# Basic configuration
BITRATE             = "f_clock_mhz=40,nom_brp=1,nom_tseg1=63,nom_tseg2=16,nom_sjw=16,data_brp=2,data_tseg1=14,data_tseg2=5,data_sjw=4"
DEV_ID_LIST         = ["0", "1", "2"]
RECV_MSG_ID_LIST    = {"": "FL", "": "FR", "": "RL", "": "RR", "": "TG"}

# FL's recive MSG_ID → 
# FR's recive MSG_ID → 
# RL's recive MSG_ID → 
# RR's recive MSG_ID → 
# Talegate's recive MSG_ID → '0x547', '0x17C5F801', '0x17FC0014', '1FF11400(Temperature)'

# Door test message preset
DOOR_MSG_ID_LIST    = {"1E1": "FL", "1E2": "FR", "1E3": "RL", "1E4": "RR"}
DOOR_DLC            = 16
DOOR_ACT            = ["00", "00", "00", "00", "00", "01" "00", "00", "00", "00", "00", "00", "00", "00", "00", "00"]
DOOR_DEACT          = ["00", "00", "00", "00", "00", "00" "00", "00", "00", "00", "00", "00", "00", "00", "00", "00"]
DOOR_RCV_MSG_ID_FL  = ["0x123", "1234", "12345"]
DOOR_RCV_MSG_ID_FR  = ["0x123", "1234", "12345"]
DOOR_RCV_MSG_ID_RL  = ["0x123", "1234", "12345"]
DOOR_RCV_MSG_ID_RR  = ["0x123", "1234", "12345"]

# Talegate test message preset
TALEGATE_MSG_ID     = ["18060501"]
TALEGATE_DLC        = 8
TALEGATE_ACT        = ["00", "00", "00", "00", "00", "01", "00", "00"]
TALEGATE_DEACT      = ["00", "00", "00", "00", "00", "00", "00", "00"]
TALEGATE_RCV_MSG_ID = ["0x547", "0x17c5f801", "0x17FC0014", "0x1FF11400"]

# Common message preset
COMMON_TEMP1        = ["03", "0E", "02", "01", "55", "55", "55", "55"]
COMMON_TEMP2        = ["03", "0C", "02", "04", "55", "55", "55", "55"]
COMMON_TEMP3        = ["03", "15", "02", "01", "55", "55", "55", "55"]
