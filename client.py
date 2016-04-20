#Simple-FTP sender
import socket
import sys
import collections
import pickle
import signal
import threading
from multiprocessing import Lock
from collections import namedtuple
import time

#Variables
N = 0
RTT = 0.1
TYPE_DATA = "0101010101010101"
TYPE_ACK = "1010101010101010"
TYPE_EOF = "1111111111111111"
ACK_HOST = '10.139.63.147'
ACK_PORT = 65000
max_seq_number=0
last_ack_packet = -1
last_send_packet = -1 # ACK received from server.
sliding_window = set() #Ordered dictionary
client_buffer = collections.OrderedDict() #Ordered dictionary
thread_lock = Lock()
data_packet = namedtuple('data_packet', 'sequence_no checksum type data')
ack_packet = namedtuple('ack_packet', 'sequence_no padding type')
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sending_completed=False

t_start=0
t_end=0

SEND_HOST = '152.14.142.101'#socket.gethostbyname(socket.gethostname())
SEND_PORT = 7735
FILE_NAME = sys.argv[3]
N = sys.argv[4]	
MSS = sys.argv[5]

def send_packet(packet, host, port, socket, sequence_no):
	client_socket.sendto(packet,(SEND_HOST,SEND_PORT)) #(SEND_HOST, SEND_PORT))
	print "packet "+str(sequence_no)+" sent"

def rdt_send(file_content, client_socket, host, port):
	global last_send_packet,last_ack_packet,sliding_window,client_buffer,t_start
	print host
	print port
	t_start=time.time()
	while len(sliding_window)<min(len(client_buffer),N):
		if last_ack_packet==-1:
			send_packet(client_buffer[last_send_packet+1], host, port, client_socket, last_send_packet+1)
			print 'rdt sent '+str(last_send_packet+1)
			signal.alarm(0)
 			signal.setitimer(signal.ITIMER_REAL, RTT)
			last_send_packet = last_send_packet + 1
			sliding_window.add(last_send_packet)
			y=0
			while y<100000:
				y=y+1
	print 'rdt done'
	
def compute_checksum_for_chuck(chunk):
	checksum=0
	l=len(chunk)
	#print l
	chunk=str(chunk)
	byte=0
	#print 'ooooo'
	while byte<l:
		#print byte
		byte1=ord(chunk[byte])
		shifted_byte1=byte1<<8
		if byte+1==l:
			#print 'lllllll'
			byte2=0xffff
		else:
			byte2=ord(chunk[byte+1])
		merged_bytes=shifted_byte1+byte2
		checksum_add=checksum+merged_bytes
		carryover=checksum_add>>16
		main_part=checksum_add&0xffff
		checksum=main_part+carryover
		byte=byte+2
	checksum_complement=checksum^0xffff
	return checksum_complement

def ack_process():
	global last_ack_packet,last_send_packet,client_buffer,sliding_window,client_socket,SEND_PORT,SEND_HOST,sending_completed,t_end,t_start,t_total
	ack_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	ack_socket.bind((ACK_HOST, ACK_PORT))
	while 1:
		print 'waiting'
		reply = pickle.loads(ack_socket.recv(65535))
		print 'got ack for '+str(reply[0]-1)
		if reply[2] == TYPE_ACK:
			print 'processing ack for '+str(reply[0]-1)
			current_ack_seq_number=reply[0]-1
			if last_ack_packet >= -1:
				print 'ack'
				thread_lock.acquire()
				print 'ack lock acq for '+str(reply[0]-1)
				print 'last ack packet ' + str(last_ack_packet)
    			if current_ack_seq_number == max_seq_number:
    				eof_packet = pickle.dumps(["0", "0", TYPE_EOF, "0"])
    				client_socket.sendto(eof_packet, (SEND_HOST, SEND_PORT))
    				thread_lock.release()
    				print 'lock rel up'+str(reply[0]-1)
    				sending_completed=True
    				t_end=time.time()
    				print "Start Time: "+str(t_start)
    				print "End Time: "+str(t_end)
    				t_total=t_end-t_start
    				print "Total Time: "+str(t_total)
    				with open('time.txt', 'ab') as file:
    					file.write(str(t_total)+'\n')
    				break
    			elif current_ack_seq_number>last_ack_packet:
    				print 'inside ack accepting for packet '+str(reply[0]-1)
        			while last_ack_packet<current_ack_seq_number:
        				signal.alarm(0)
        				signal.setitimer(signal.ITIMER_REAL, RTT)
        				last_ack_packet=last_ack_packet+1
        				print sliding_window
        				sliding_window.remove(last_ack_packet)
        				client_buffer.pop(last_ack_packet)
        				while len(sliding_window)<min(len(client_buffer),N):
	        				if last_send_packet<max_seq_number:
	        					send_packet(client_buffer[last_send_packet+1],SEND_HOST,SEND_PORT,client_socket,last_send_packet+1)
	        					sliding_window.add(last_send_packet+1)
	        					last_send_packet=last_send_packet+1
        			thread_lock.release()
        			print 'lock rel mid'+str(reply[0]-1)
        		else:
        			thread_lock.release()
        			print 'lock rel down'+str(reply[0]-1)
        	print'done again'

def timeout_thread(timeout_th, frame):
	global last_ack_packet
 	if last_ack_packet==last_send_packet-len(sliding_window):
 		print "packet "+str(last_ack_packet+1)+" timer expired"
 		thread_lock.acquire()
 		for i in range(last_ack_packet+1,last_ack_packet+1+len(sliding_window),1):
 			signal.alarm(0)
 			signal.setitimer(signal.ITIMER_REAL, RTT)
			send_packet(client_buffer[i], SEND_HOST, SEND_PORT, client_socket, i)
		thread_lock.release()
	

def main():
	global client_buffer ,max_seq_number,client_socket,N,SEND_PORT,SEND_HOST,MSS

	port = SEND_PORT
	host = SEND_HOST
	N = int(N)
	mss = int(MSS)
	
	#UDP datagram socke
	
	max_window_size = N - 1
	
	sequence_number = 0
	try:
		with open(FILE_NAME, 'rb') as f:
			while True:
				print 'here'
				chunk = f.read(int(mss))  
				if chunk:
					max_seq_number=sequence_number
					chunk_checksum=compute_checksum_for_chuck(chunk)
					client_buffer[sequence_number] = pickle.dumps([sequence_number,chunk_checksum,TYPE_DATA,chunk])
					print max_seq_number
					sequence_number=sequence_number+1
				else:
					break
	except:
		sys.exit("Failed to open file!")

	signal.signal(signal.SIGALRM, timeout_thread)
	ack_thread = threading.Thread(target=ack_process)
	ack_thread.start() 	
	rdt_send(client_buffer, client_socket, host, port)
	while 1:
		if sending_completed:
			break
	
	ack_thread.join()
	client_socket.close()

if __name__ == "__main__":
    main()

