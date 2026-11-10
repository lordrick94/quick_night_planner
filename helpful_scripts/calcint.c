/* this is the cassegrain tub readout interpolation function */
/* a driver for this is called icass.c */

# define SIZE 37
float tubarr [SIZE] [2] = {
   {  20,  17.45 },
   {  30,  26.15 },
   {  40,  34.85 },
   {  50,  43.55 },
   {  60,  52.25 },
   {  70,  60.95 },
   {  80,  69.65 },
   {  90,  78.35 },
   { 100,  87.05 },
   { 110,  95.75 },
   { 120,  104.45 },
   { 130,  113.15 },
   { 140,  121.85 },
   { 150,  130.55 },
   { 160,  139.25 },
   { 170,  147.95 },
   { 180,  156.65 },
   { 190,  165.35 },
   { 200,  174.05 },
   { 210,  182.75 },
   { 220,  191.45 },
   { 230,  200.15 },
   { 240,  208.85 },
   { 250,  217.55 },
   { 260,  226.25 },
   { 270,  234.95 },
   { 280,  243.65 },
   { 290,  252.35 },
   { 300,  261.05 },
   { 310,  269.74 },
   { 320,  278.44 },
   { 330,  287.14 },
   { 340,  295.84 },
   { 350,  304.54 },
   { 360,  313.24 },
   { 370,  321.94 },
   { 380,  330.64 }
};

float calcint(pa)
float pa;
   {
   int i;
   float val, slope, negap[2], posap[2];
   /* these last two are arrays that will be used to find the closest
   two angles in the list to the given angle.  the array negap
   will hold the difference between the given angle and an angle
   less than it, with the second element the encoder number.
   Similarly for the positive one.*/


   posap[0]=  1000;
   negap[0] = -1000;
      /* initialize */

      if (0 <= pa && pa < 20)
	 {
         pa += 360;
	 }
	     /* put into 360-380 degree range */

      for (i=0; i <= SIZE-1; i++)
	 {
         val = pa - tubarr[i] [0];

         if (val == 0) return(tubarr[i] [1]);
	     /* exact angle in list */
         else if (val < 0) 
	    {
	    if (val > negap[0])  
	       /* found angle closer to given angle */
	       {
	       negap[0] = val;
	       negap[1] = tubarr[i] [1];
	       }
	    }

         else if (val > 0) 
	    {
	    if (val < posap[0])  
	       /* found angle closer to given angle */
	       {
	       posap[0] = val;
	       posap[1] = tubarr[i] [1];
	       }
	    }
	 }

	 /* do interpolation explicitly */
	

	 slope = (posap[1] - negap[1])/(posap[0] - negap[0]);
	 return(-slope*posap[0] + posap[1]);
}
