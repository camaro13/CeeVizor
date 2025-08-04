
set pagination off
start
while $pc
  printf "##STEP##\n"
  frame
  info line
  info locals
  step
end
quit
