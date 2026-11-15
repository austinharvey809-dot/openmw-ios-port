#pragma once
#include <osg/Vec3d>
#include <algorithm>
#include <cmath>
namespace G2 {
class Navigation {
    osg::Vec3d initial;
    double initialYaw=0,previous=-1;
public:
    osg::Vec3d eye;
    double yaw=0,pitch=0;
    float strafe=0,forward=0,vertical=0,lookX=0,lookY=0;
    void start(osg::Vec3d entry,double angle){initial=entry;initialYaw=angle;reset();}
    void reset(){eye=initial;yaw=initialYaw;pitch=0;previous=-1;}
    void suspend(){previous=-1;strafe=forward=vertical=lookX=lookY=0;}
    void turn(double x,double y){if(std::isfinite(x)&&std::isfinite(y)){yaw+=x;pitch=std::clamp(pitch+y,-1.4,1.4);}}
    void update(double now){
        if(!std::isfinite(now))return;
        const double dt=previous<0?0:std::clamp(now-previous,0.,.05);previous=now;
        auto axis=[](float x){return std::isfinite(x)&&std::abs(x)>.15f?std::clamp(x,-1.f,1.f):0.f;};
        turn(-axis(lookX)*dt*1.8,axis(lookY)*dt*1.8);
        osg::Vec3d move(std::cos(yaw)*axis(strafe)-std::sin(yaw)*axis(forward),
                       std::sin(yaw)*axis(strafe)+std::cos(yaw)*axis(forward),axis(vertical));
        if(move.length2()>1)move.normalize();eye+=move*(180*dt);
    }
    osg::Vec3d direction() const{return {-std::sin(yaw)*std::cos(pitch),std::cos(yaw)*std::cos(pitch),std::sin(pitch)};}
};
}
