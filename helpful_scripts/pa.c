


/*    Written by Jim Burrous, Lick Observatory, 1990
		  Jim%UCSCLOC.UCSC.EDU
	
	Utility will take as input HA, DEC, and EXPOSURE in seconds.

	Returns PA, air mass, for middle of exposure.  
	Also returns encoding for Cassegrain tub position (calls CALCINT.C).
	in Nixie readout units
	This program is based on a PASP by Alex Filippenko from 1982

								      */

# include <math.h>
# include <stdio.h>
# define LICK_LAT 37.343                   /*        Lick Obs.          */ 
# define PAL_LAT 33.3567                   /*        Palomar Obs.       */
# define KECK_LAT 19.825		   /*        Keck Obs.		*/
# define RAD 3.1415927/180.

main()
{
    float dha, dec, ha, ha_start, ha_test, min, time, pa;
    float alt_pa, alt_tub, casstub, calcint();
    int n, m;
    double eta, tmp, num, denom, lat;
    double getsex(int is_HA, FILE *fp);
    char again;

    char buf[200], buf2[200];

    lat = LICK_LAT;
    lat *= RAD;


    printf("\n This program computes the tub angle that minimizes"
					    " loss of light due to\n");
    printf(" differential atmospheric refraction.\n\n");

    ha_start = getsex(1, stdin);
    dec = getsex(0, stdin);

    printf ("Length of Exposure (sec): ");
    if (!fgets(buf, sizeof(buf), stdin))
	exit(0);
    sscanf(buf, "%f", &time);

    /* time is measured in seconds */

    ha = ha_start + .5*time/3600;
    /* HA used is midpoint of exposure */
    ha *= (RAD*15);
    dec *= RAD;
    dha = ha ;
    ha = (dha<0) ? -ha : ha; /* must use positive ha */

    num = sin(ha)*cos(lat);
    tmp = (sin(lat)*sin(dec) + cos(lat)*cos(dec)*cos(ha));
    denom = sqrt(1.-pow(tmp, 2.));
    eta = (1./(RAD)) * asin(num/ denom);

    if (dec >= lat) {
	ha_test = acos(tan(lat)/tan(dec)); /* Need to check around HA=90 */
	if (ha <= ha_test) {
	    eta = 180. - eta;
	}
    }
    eta = (dha < 0) ? 360-eta : eta ;
    eta = (eta >= 180) ? (eta - 180) : (eta + 180) ;
    pa = eta;
    alt_pa = (pa >= 180) ? (pa - 180) : (pa + 180) ;

    printf("\nStarting HA = %.2f", ha_start);
    printf("\tDec = %.2f",(dec/(RAD)));
    printf("\tTime = %.0f seconds",time);
    printf("\n\nPA (average) = %.0f (or %.0f)\tAirmass (average) = %.2f",
	pa, alt_pa, 1/tmp);

    casstub = calcint(pa);
    alt_tub = calcint(alt_pa);

    /* output with correct number of decimal points */
    if (casstub <= 99.99)
	printf("\nNixie readout = %.2f (or %.2f)\n", casstub, alt_tub);
    else
	printf("\nNixie readout = %.1f (or %.1f)\n", casstub, alt_tub);
    printf("\n\n");
}


double
getsex(int is_HA, FILE *fp)
{
    char buf[400], buf2[400], *p;
    int m, n;
    double x;

    char *ha_prompt = "HA (hh.hh, hh:mm, or  hh mm)";
    char *dec_prompt = "Dec (dd.dd, dd:mm, or  dd mm)";

    for (buf[0] = '\0'; buf[0] == '\0'; ) {
	printf ("Enter starting %s: ", is_HA ? ha_prompt : dec_prompt);
	if (!fgets(buf, sizeof(buf), fp))
	    exit(0);

	/* Trim trailing w/s... */
	for (p=buf+strlen(buf); p > buf && isspace(*(p-1)); p--)
	    ;
	/* ...and make string end with newline as a marker char */
	strcpy(p, "\n");

	/* Validate the buffer. */
	if (sscanf(buf, "%d.%d%[\n]", &m, &n, buf2) == 3) {
	    if (sscanf(buf, "%lf", &x) != 1) {
		printf("Error scanning <%s>", buf);
		buf[0] = '\0';
	    }
	} else if (sscanf(buf, "%d:%d%[\n]", &m, &n, buf2) == 3 ||
		    sscanf(buf, "%d %d%[\n]", &m, &n, buf2) == 3) {
	    if (m < 0 && n < 0) {
		printf("Don't understand `%s'; try again.", buf);
		buf[0] = '\0';
	    } else if (m < 0) {
		n = -n;
	    } else if (n < 0) {
		m = -m;
	    }
	    x = (float) m + (float) n / 60.;
	} else {
	    printf("Don't understand `%s'; try again.", buf);
	    buf[0] = '\0';
	}
    }
    /* Check for leading minus sign, in case it got lost as part of "-0"...
     * if it's there, and ha > 0, change sign of ha.
     */
    if (x > 0 && sscanf(buf, "%s", buf2) == 1 && *buf2 == '-')
	x = -x;

    return x;
}
