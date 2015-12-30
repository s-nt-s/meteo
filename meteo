#!/usr/bin/perl -w

use strict;
use warnings;

use XML::Simple;
use LWP::Simple;

sub dataI {
    my $d=$_[0];
    my $gb=$_[1];
    
    return (
           $d->{estado_cielo}->[$gb]->{descripcion},
           $d->{temperatura}->{minima},
           $d->{temperatura}->{maxima},
           $d->{sens_termica}->{minima},
           $d->{sens_termica}->{maxima},
           $d->{prob_precipitacion}->[$gb]->{content},
           $d->{humedad_relativa}->{minima},
           $d->{humedad_relativa}->{maxima},
           $d->{viento}->[$gb]->{velocidad}
           #,$d->{viento}->[$gb]->{direccion}
           #,$d->{cota_nieve_prov}->[$gb]->{content}
    );
};
sub showI {
    print "Estado del cielo:\t" . $_[0] . "\n";

    my $t1=$_[1];
    my $t2=$_[2];
    my $s1=$_[3];
    my $s2=$_[4];

    print "Temp. min./max.:\t" . $t1 . " / " . $t2;
    if (abs($t1-$s1)>1 || abs($t2-$s2)>1) {print " [" . $s1 . " / " . $s2 . "] ";}
    print "°C\n";
    print "Precipitaciones:\t" . $_[5] . " %\n";
    print "Humedad relativa:\t" . $_[6] . " / " . $_[7] . " %\n";
    print "Viento:\t\t\t" . $_[8] . " km/h\n";
};
sub dataM {
    my $d=$_[0];
    my $gb=$_[1];
    my $sc=$_[2];
    my $cc = ($sc==-1?0:$sc);
    my $ss = (($sc==3?3:4)+$sc);

    return (
           $d->{estado_cielo}->[$ss]->{descripcion},
           $d->{temperatura}->{dato}->[$cc]->{content},
           $d->{sens_termica}->{dato}->[$cc]->{content},
           $d->{prob_precipitacion}->[$ss]->{content},
           $d->{humedad_relativa}->{dato}->[$cc]->{content},
           $d->{viento}->[$ss]->{velocidad}
    );
};
sub showM {
    my $th=$_[1];
    my $sh=$_[2];

    print $_[0] . ", " . $th;
    if (abs($th-$sh)>1) {print " [" . $sh . "] ";}
    print "°C, ";
    if ($_[3]>0) {print $_[3] . "% lluvia, ";}
    print $_[4] . "% humedad, ". $_[5] ."km/h viento\n";
};

sub prt {
    my $len=($_[1] || length($_[0]))+4;
    my $msg="= ". $_[0] . " =";
    my $z=int((20 - $len)/2);
    if ($z >0) {
	for (my $count = $z ; $count > 0; $count--) {$msg="=" . $msg . "=";}
	if (($len % 2) == 1) {$msg=$msg . "=";}
    }
    print $msg . "\n";
};

sub cmparr {
	my @a = $_[0];
	my @b = $_[1];
	if (@a != @b) {
		return 0;
	}
	foreach (my $i = 0; $i < @a; $i++) {
	    if ($a[$i] != $b[$i]) {
	        return 0;
	    }
	}
	return 1;
}

my $url = $ARGV[0] || '';

if ($url eq '') {
	die "Ha de pasar como parametro la url de un xml de www.aemet.es"
}
# m = atajo para Madrid
elsif ($url eq "m") {$url="http://www.aemet.es/xml/municipios/localidad_28079.xml";}

my $content = get $url or die "URL erronea (Ha de pasar como parametro la url de xml de www.aemet.es)";
$content =~ s/ISO-8859-15/ISO-8859-2/;
my $xml =eval{XMLin($content)};
if ( $@ ) { 
   die "XML erroneo (Ha de pasar como parametro la url de un xml de www.aemet.es)";
} 

my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time());
my $flag=($year+1900) . "-" . ($mon<9?"0":"") . ($mon+1) . "-" . ($mday<10?"0":"") . $mday;

my $hoy;
my $z=scalar(@{$xml->{prediccion}->{dia}});
my $index=0;

for ($index = 0; ($index < $z && (! defined($hoy))); $index++) {
    if ($xml->{prediccion}->{dia}->[$index]->{fecha} eq $flag) {$hoy=$xml->{prediccion}->{dia}->[$index];}
}

if ( ! defined($hoy)) {
   die "XML erroneo (Ha de pasar como parametro la url de un xml de www.aemet.es)";
}

my $gb = ($hour>16) ? 6 : ( ($hour>10) ? 2 : 0 ) ;
my $sc = ($hour>22) ? 3 : ( ($hour>16) ? 2 : ( ($hour>10) ? 1 : ( ($hour>5) ? 0 : -1 )  ) ) ;

my $ig=1;
my $ct=uc($xml->{nombre});

my @a=dataM($hoy,$gb,$sc);
if ($gb != 6) {
   my @n=dataM($hoy,6,3);
   $ig=cmparr(\@a, \@n);
   if (! $ig) {
      prt($ct);
      print "Ahora: ";
      showM(@a);
      print "Noche: ";
      showM(@n);
   }
}
if ($ig) {
   prt($ct . " ahora");
   showM(@a);
}
print "\n";

$ig=1;
if ($gb == 0) {
   my @m=dataI($hoy,1);
   my @t=dataI($hoy,2);
   $ig=cmparr(\@m, \@t);
   if (! $ig) {
      prt("HOY: mañana");
      showI(@m);
      print "\n";
      prt("HOY: tarde");
      showI(@t);
   }
}
if ($ig) {
   my $tow = $xml->{prediccion}->{dia}->[$index];
   prt("HOY");
   showI(dataI($hoy,$gb));
   print "\n";
   prt("MAÑANA",6);
   showI(dataI($tow,0));
}

print "\nFuente: " . $xml->{origen}->{enlace} . "\n";
