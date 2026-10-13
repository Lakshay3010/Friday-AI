import pyttsx3
import time

for sentence in ["Hello Lakshay", "This is sentence two", "This is sentence three"]:
    print(f"Speaking: {sentence}")
    e = pyttsx3.init()
    e.say(sentence)
    e.runAndWait()
    e.stop()
    del e
    time.sleep(0.5)
    print("Done")