set pagination off
set print pretty off
skip function printf
skip function fprintf
skip function vfprintf
skip function vprintf
skip function puts
skip function putchar
skip function _IO_printf
skip function __stdio_common_vfprintf
skip function __acrt_iob_func

start
while $pc
  printf "##STEP##\n"
  frame
  info line
  info locals
  printf "__GV_BEGIN__\n"
  printf "__GV__ counter="
  output counter
  printf "\n"
  printf "__GV__ msg[20]=%s\n", (char*) msg
  printf "__GV_END__\n"
  printf "__BT_BEGIN__\n"
  bt
  printf "__BT_END__\n"
  step
end
quit